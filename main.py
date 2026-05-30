import asyncio
import cv2
from loguru import logger
from ImgTrans import SendImgUDP
from utils import Cap, Uart, is_desktop_environment
from applications import Applications
import platform
from utils import Switch, LED, OLED_I2C
import time


_log = logger.bind(module="App")
applications = Applications(config_path="config.yaml")
switch = Switch("GPIO3-A3", True)
start_LED = LED("GPIO3-A2")
detecting_LED = LED("GPIO3-A4")
oled = OLED_I2C(2,0x3c)


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


NETWORK_INTERFACES = ["eth0", "wlan0"]
SERVER_PORT = 8080
SERIAL_PORT = "/dev/ttyS3"

if platform.system() == "Linux":
    CAP = Cap() # 初始化摄像头（Linux环境）
else:
    CAP = cv2.VideoCapture(0) # 初始化摄像头（Windows环境）

# 定义任务表
TASK_TABLE = {
    "R": (applications.detect_material, "R"),
    "G": (applications.detect_material, "G"),
    "B": (applications.detect_material, "B"),
    "C": (applications.detect_circle, None)
}


async def main(cap: cv2.VideoCapture, ser_port: str = "/dev/ttyUSB0"):
    global img_need_to_send, content_need_to_show

    ser = Uart(ser_port)

    while True:
        # 获取当前运行模式
        async with mode_lock:
            run_mode = RUN_MODE
        if run_mode == "main":
            # 读取串口任务
            task_sign = await ser.new_read(head="@", tail="#")
            if task_sign is None:
                _log.warning("未收到任务")
                continue
            _log.info(f"收到任务: {task_sign}")

            ret, img = cap.read()
            if not ret:
                _log.warning("无法读取摄像头图像")
                break

            # 处理图像
            else:
                await detecting_LED.on()
                # TASK_TABLE[task_sign][0]为函数指针
                # TASK_TABLE[task_sign][1]为附加参数
                start_time = time.perf_counter()
                res, res_img = await TASK_TABLE[task_sign][0](img, TASK_TABLE[task_sign][1])
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


def _resolve_interface() -> str:
    """按优先级尝试网卡列表，返回第一个有有效IP的网卡名称。"""
    for iface in NETWORK_INTERFACES:
        ip = SendImgUDP.get_ip_address(iface)
        if ip:
            _log.info(f"网卡 {iface} 已就绪, IP: {ip}")
            return iface
        _log.warning(f"网卡 {iface} 无有效IP地址, 尝试下一个...")
    _log.warning("所有网卡均无有效IP地址, 将绑定 0.0.0.0")
    return ""

async def img_trans():
    global img_need_to_send, server_ip
    # 通过网卡设备自动获取IP地址（含 eth0 -> wlan0 优先级回退）
    interface = _resolve_interface()
    sendImgUDP = await SendImgUDP.create(interface=interface, port=SERVER_PORT)
    host_ip = sendImgUDP.host_ip
    _log.info(f"服务端IP: {host_ip if host_ip else '未连接(将监听所有接口)'}")
    async with server_ip_lock:
        server_ip = host_ip

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

async def run():
    await asyncio.gather(main(CAP, SERIAL_PORT), board_show(), img_trans())

def cli():
    asyncio.run(run())

if __name__ == "__main__":
    cli()
# end main
