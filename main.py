import asyncio
import cv2
import platform
import time
from pathlib import Path

import yaml
from loguru import logger

from ImgTrans import SendImgUDP
from core.config_bridge import SystemConfig
from applications import Applications
from utils import Cap, Uart, is_desktop_environment
from utils import Switch, LED, OLED_I2C
from utils.file_hash import compute_file_hash
from utils.hardware_noop import NoOpLED, NoOpSwitch, NoOpOLED


_log = logger.bind(module="App")

CONFIG_PATH = "config.yaml"

# 全局硬件句柄，在 run() 中初始化
applications: Applications | None = None
switch: Switch | NoOpSwitch | None = None
start_LED: LED | NoOpLED | None = None
detecting_LED: LED | NoOpLED | None = None
oled: OLED_I2C | NoOpOLED | None = None
CAP: cv2.VideoCapture | Cap | None = None

# 待发送图像及锁
img_need_to_send = None
img_lock = asyncio.Lock()

# 运行模式，包含 main 和 debug
# main模式运行任务，debug模式仅仅发送图像
RUN_MODE = "main"
mode_lock = asyncio.Lock()

# 需要显示在OLED上的信息主体及锁
content_need_to_show = ""
content_lock = asyncio.Lock()

# 服务端IP及锁
server_ip = ""
server_ip_lock = asyncio.Lock()


class InitializationError(Exception):
    """初始化阶段出现无法继续运行的致命错误"""
    pass


def _load_system_config(path: str) -> SystemConfig:
    """从 config.yaml 中读取 system 段，失败时抛出异常。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError("配置文件内容不是有效的字典")
    return SystemConfig.from_dict(raw.get("system", {}))


async def _initialize() -> SystemConfig:
    """集中初始化所有硬件与核心对象，失败时抛出 InitializationError。"""
    global applications, switch, start_LED, detecting_LED, oled, CAP

    # 1. 配置文件
    config_file = Path(CONFIG_PATH)
    if not config_file.exists():
        _log.error(f"缺少配置文件: {CONFIG_PATH}，请先创建该文件")
        raise InitializationError("缺少配置文件")

    try:
        system = _load_system_config(CONFIG_PATH)
    except Exception as e:
        _log.error(f"config.yaml 加载失败，请检查文件格式与字段: {e}")
        raise InitializationError("配置加载失败") from e

    try:
        applications = Applications(config_path=CONFIG_PATH)
    except Exception as e:
        _log.error(f"检测器初始化失败，请检查 config.yaml 中颜色/色环参数: {e}")
        raise InitializationError("检测器初始化失败") from e

    # 2. 摄像头
    try:
        if platform.system() == "Linux":
            if system.camera_index is not None:
                CAP = Cap(_id=system.camera_index)
            else:
                CAP = Cap()
        else:
            idx = system.camera_index if system.camera_index is not None else 0
            CAP = cv2.VideoCapture(idx)
        if not CAP.isOpened():
            raise RuntimeError("摄像头未能成功打开")
    except Exception as e:
        _log.error(f"摄像头打开失败，请检查设备连接与权限: {e}")
        raise InitializationError("摄像头初始化失败") from e

    # 3. GPIO / LED / 开关（非关键硬件，失败时使用 no-op 占位）
    try:
        switch = Switch(system.switch_pin, system.switch_reverse)
        start_LED = LED(system.start_led_pin)
        detecting_LED = LED(system.detecting_led_pin)
    except Exception as e:
        _log.warning(f"GPIO 初始化失败，程序将继续运行但 LED/开关不可用: {e}")
        switch = NoOpSwitch()
        start_LED = NoOpLED()
        detecting_LED = NoOpLED()

    # 4. OLED（非关键硬件，失败时使用 no-op 占位）
    try:
        oled = OLED_I2C(system.oled_i2c_port, system.oled_i2c_address)
    except Exception as e:
        _log.warning(f"OLED 初始化失败，程序将继续运行但 OLED 不可用: {e}")
        oled = NoOpOLED()

    _log.info("系统初始化完成")
    return system


async def main(cap: cv2.VideoCapture, ser: Uart, task_table: dict):
    global img_need_to_send, content_need_to_show

    assert applications is not None, "applications 未初始化"
    assert detecting_LED is not None, "detecting_LED 未初始化"

    while True:
        # 获取当前运行模式
        async with mode_lock:
            run_mode = RUN_MODE
        if run_mode == "main":
            # 串口断开后自动重连
            if not ser.is_open:
                _log.warning("串口未打开，尝试重连...")
                if not await ser.reconnect():
                    await asyncio.sleep(1.0)
                    continue
                _log.info("串口已重连")

            # 读取串口任务
            task_sign = await ser.new_read(head="@", tail="#")
            if task_sign is None:
                if not ser.is_open:
                    # 读取过程中串口断开，直接进入下一轮重连
                    continue
                # 超时未收到任务，避免空转，短暂让出事件循环
                await asyncio.sleep(0.05)
                continue
            _log.info(f"收到任务: {task_sign}")

            ret, img = cap.read()
            if not ret:
                _log.warning("无法读取摄像头图像")
                break

            # 处理图像
            else:
                await detecting_LED.on()
                # task_table[task_sign][0]为函数指针
                # task_table[task_sign][1]为附加参数
                start_time = time.perf_counter()
                res, res_img = await task_table[task_sign][0](img, task_table[task_sign][1])
                res_str = applications.tuple2str(res)
                async with content_lock:        # 保护内容更新
                    content_need_to_show = str(res) if res else 'None'

                await ser.new_write(res_str, head="@", tail="#")
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                _log.info(f"发送结果: {res_str} (耗时: {elapsed_ms:.2f} ms)")

                await detecting_LED.off()

                async with img_lock:
                    img_need_to_send = res_img.copy()

            # 仅在桌面环境下显示图像
            if is_desktop_environment():
                cv2.imshow("Frame", img)
                cv2.imshow("Res Frame", res_img)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
        else:
            ret, img = cap.read()
            if not ret:
                _log.warning("无法读取摄像头图像")
                await asyncio.sleep(0.1)
                continue
            # 复制图像到待发送图像
            async with img_lock:
                img_need_to_send = img.copy()
            # 控制 debug 模式帧率，避免高频空转抢占事件循环
            await asyncio.sleep(0.03)
    cap.release()
    if is_desktop_environment():
        cv2.destroyAllWindows()


async def board_show():
    global RUN_MODE, content_need_to_show

    assert switch is not None, "switch 未初始化"
    assert start_LED is not None, "start_LED 未初始化"
    assert oled is not None, "oled 未初始化"

    prev_mode = None
    while True:
        show_content = ""
        switch_status = await switch.read_status()
        if switch_status:  # 图传模式（debug）
            async with mode_lock:
                RUN_MODE = "debug"
            show_content = "Debug\n"
        else:
            async with mode_lock:
                RUN_MODE = "main"
            show_content = "Main\n"
        if RUN_MODE != prev_mode:
            _log.info(f"运行模式切换: {prev_mode} -> {RUN_MODE}")
            prev_mode = RUN_MODE
            # 展示LED灯 - start_LED在main模式点亮，debug模式熄灭
            if RUN_MODE == "main":
                await start_LED.on()
            else:
                await start_LED.off()
        async with server_ip_lock:
            ip_display = server_ip if server_ip else "未连接"
            show_content += f"Server IP: {ip_display}\n"
        async with content_lock:
            show_content += content_need_to_show
        await oled.clear()
        await oled.text(show_content, (1,1))
        await oled.display()
        await asyncio.sleep(0.05)


async def config_watcher():
    """配置文件热加载监视线程

    通过周期性计算 config.yaml 的 SHA-256 hash，检测文件内容是否发生变化，
    变化时调用 Applications.reload_config() 重新加载检测器参数。
    """
    assert applications is not None, "applications 未初始化"

    _log.info(f"启动配置文件热加载监视: {CONFIG_PATH}")
    last_hash = compute_file_hash(CONFIG_PATH)

    while True:
        await asyncio.sleep(1.0)
        try:
            current_hash = compute_file_hash(CONFIG_PATH)
            if current_hash is None:
                continue
            if last_hash is None:
                last_hash = current_hash
                continue
            if current_hash != last_hash:
                _log.info("检测到配置文件变化，开始重新加载")
                await applications.reload_config()
                last_hash = current_hash
        except Exception as e:
            _log.error(f"配置文件监视异常: {e}")


async def img_trans(port: int, interface: str):
    global img_need_to_send, server_ip
    # 绑定所有网卡，UDP 图传
    sendImgUDP = await SendImgUDP.create(interface=interface, port=port)
    _log.info("UDP 服务已启动 (监听所有网卡)")

    # 从可用网卡获取一个 IP 地址用于 OLED 显示
    for iface in ("eth0", "wlan0"):
        ip = SendImgUDP.get_ip_address(iface)
        if ip:
            _log.info(f"本机IP: {ip}")
            async with server_ip_lock:
                server_ip = ip
            break

    connected = False
    while not connected:
        connected = await sendImgUDP.connecting()
        if not connected:
            await asyncio.sleep(0.1)
    _log.info(f"UDP 客户端已连接: {sendImgUDP.B_IP}")

    while True:
        # 使用锁保护读取操作
        async with img_lock:
            current_img = img_need_to_send

        if current_img is None:
            await asyncio.sleep(0.01)  # 添加微小延迟，避免空转
            continue

        # 发送图像
        try:
            await sendImgUDP.send(current_img)
        except Exception as e:
            _log.error(f"图像发送失败: {e}")

        # 发送完成后，将待传输的图像设置为None
        async with img_lock:
            img_need_to_send = None

        # 控制发送频率，避免连续高频发送抢占事件循环
        await asyncio.sleep(0.02)


async def run() -> bool:
    try:
        system = await _initialize()
    except InitializationError:
        _log.error("系统初始化失败，程序退出")
        return False

    assert applications is not None, "applications 未初始化"
    assert CAP is not None, "CAP 未初始化"

    task_table = {
        "R": (applications.detect_material, "R"),
        "G": (applications.detect_material, "G"),
        "B": (applications.detect_material, "B"),
        "C": (applications.detect_circle, None),
    }

    try:
        ser = Uart(system.serial_port)
    except Exception as e:
        _log.error(f"串口 {system.serial_port} 打开失败，请检查权限与连接: {e}")
        return False

    await asyncio.gather(
        main(CAP, ser, task_table),
        board_show(),
        img_trans(system.udp_port, system.udp_interface),
        config_watcher(),
    )
    return True


def cli():
    try:
        success = asyncio.run(run())
    except KeyboardInterrupt:
        _log.info("用户中断")
        success = False
    except Exception as e:
        _log.error(f"运行时异常: {e}")
        success = False

    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
# end main
