import asyncio
import os
import cv2
from ImgTrans import ReceiveImgUDP
import click

from applications import Applications
from utils._cap import MockImage, MockVideo  # noqa: F401
from loguru import logger

_log = logger.bind(module="setup")

# mockCap = MockImage("test.jpg")
mockCap = MockVideo(r"mock_data\test.avi")

class Setup:
    def __init__(self, cap: cv2.VideoCapture) -> None:
        self.cap: cv2.VideoCapture = cap
        self.CONFIG_PATH = "config.yaml"

        # 通过 Applications 统一初始化检测器，确保 setup 与 main 的渲染/滤波逻辑一致
        self.applications = Applications(self.CONFIG_PATH)
        self.colorDetector = self.applications.colorDetector
        self.colorRingDetector = self.applications.colorRingDetector

        # 加载已有配置（Applications 构造函数已加载，此处保留兼容逻辑）
        if os.path.exists(self.CONFIG_PATH):
            _log.info(f"已从 {self.CONFIG_PATH} 加载配置")

    async def setupColor(self):
        """
        设置颜色
        """
        self.colorDetector.createTrackbar()
        _log.info("已创建颜色设置窗口")
        cv2.namedWindow("Color", cv2.WINDOW_NORMAL)
        while True:
            ret, frame = self.cap.read()
            if frame is None:
                break

            # 使用当前 trackbar 选中的颜色标签，与 Applications/main 保持一致
            color_label = self.colorDetector.color
            res, res_img = await self.applications.detect_material(frame, color_label)

            cv2.imshow("Color", res_img)

            waitkey = cv2.waitKey(1)
            if waitkey & 0xFF == ord("q"):
                _log.info("已退出颜色设置")
                break
            elif waitkey & 0xFF == ord("s"):
                self.colorDetector.save_config(self.CONFIG_PATH)
                _log.info(f"已保存颜色配置到 {self.CONFIG_PATH}")

        cv2.destroyAllWindows()

    async def setupColorRing(self):
        """
        设置色环检测参数
        """
        self.colorRingDetector.createTrackbar()
        _log.info("已创建色环检测设置窗口")
        cv2.namedWindow("ColorRing", cv2.WINDOW_NORMAL)
        while True:
            ret, frame = self.cap.read()
            if frame is None:
                break

            filtered_center, res_img = await self.applications.detect_circle(frame)

            cv2.imshow("ColorRing", res_img)

            waitkey = cv2.waitKey(1)
            if waitkey & 0xFF == ord("q"):
                _log.info("已退出色环检测设置")
                break
            elif waitkey & 0xFF == ord("s"):
                self.colorRingDetector.save_config(self.CONFIG_PATH)
                _log.info(f"已保存色环检测配置到 {self.CONFIG_PATH}")

        cv2.destroyAllWindows()

@click.group()
def cli():
    """硬件参数调试工具"""
    pass

@cli.command()
@click.option("--remote", is_flag=True, default=False, help="是否远程摄像头")
@click.option("--capip", type=str, default="", help="摄像头IP地址，仅在remote为True时有效，填写图传发送端的IP地址")
@click.option("--port", type=int, default=None, help="摄像头端口号，仅在remote为True时有效，填写图传发送端的端口号")
@click.option("--capid", type=int, default=0, help="摄像头ID号")
def color(remote: bool = False, capip: str = "", port: int|None = None, capid: int = 0):
    """初始化颜色参数"""
    _log.info("开始初始化颜色参数")
    if remote and capip and port:
        cap = ReceiveImgUDP(capip, port, "169.254.213.183")
        _log.info("已创建远程摄像头")
    else:
        cap = cv2.VideoCapture(capid)
        _log.info(f"已创建本地摄像头 {capid}")

    setup = Setup(cap)
    _log.info("已初始化参数调节器")
    asyncio.run(setup.setupColor())

@cli.command()
@click.option("--remote", is_flag=True, default=False, help="是否远程摄像头")
@click.option("--capip", type=str, default="", help="摄像头IP地址，仅在remote为True时有效，填写图传发送端的IP地址")
@click.option("--port", type=int, default=None, help="摄像头端口号，仅在remote为True时有效，填写图传发送端的端口号")
@click.option("--capid", type=int, default=0, help="摄像头ID号")
def colorring(remote: bool = False, capip: str = "", port: int | None = None, capid: int = 0):
    """初始化色环检测参数"""
    _log.info("开始初始化色环检测参数")
    if remote and capip and port:
        cap = ReceiveImgUDP(capip, port, "169.254.213.183")
        _log.info("已创建远程摄像头")
    else:
        cap = cv2.VideoCapture(capid)
        # cap = mockCap
        _log.info(f"已创建本地摄像头 {capid}")

    setup = Setup(cap)
    _log.info("已初始化参数调节器")
    asyncio.run(setup.setupColorRing())

if __name__ == "__main__":
    cli()