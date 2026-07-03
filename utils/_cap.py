"""
Copyright (C) 2025 IVEN-CN(He Yunfeng) and Anan-yy(Weng Kaiyi)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import cv2
from collections import deque
import subprocess
import re


class Cap(cv2.VideoCapture):
    @staticmethod
    def getCapIndex():
        try:
            result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True, check=True)
            pattern = r"icspring camer.*?\n\s*(/dev/video\d+)\n\s*(/dev/video\d+)"
            match = re.search(pattern, result.stdout, re.DOTALL)
            if match:
                video1 = match.group(1)
                video2 = match.group(2)
                video1_num = re.search(r'\d+', video1).group()
                video2_num = re.search(r'\d+', video2).group()
                return video1_num, video2_num
        except subprocess.CalledProcessError as e:
            print(f"Error occurred: {e}")
            return None

    # 识别的时候需要裁剪掉的底部区域高度(px)
    NEED2CUT:int = 0

    @property
    def DETECT_HEIGHT(self):
        """
        裁剪的时候需要保留的高度
        """
        res = self.height - self.NEED2CUT
        return res if res > 0 else self.height

    def __init__(self, _id: int|None = None, w: int = 640, h: int = 480, fps: int = 60) -> None:
        if _id is None:
            caps = Cap.getCapIndex()
            if caps:
                _id = int(caps[0])
            else:
                _id = 0
        self.width = w
        self.height = h
        super().__init__(_id)
        self.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.set(cv2.CAP_PROP_FPS, fps)
        self.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc("M", "J", "P", "G"))
        self.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self, image: cv2.typing.MatLike | None = None):
        """
        读取摄像头数据
        ----
        Returns:
            tuple: (ret, frame)
        """
        ret, frame = super().read()
        if ret:
            # 裁剪底部区域
            frame = frame[0:self.DETECT_HEIGHT, :]
            return ret, frame
        return ret, None


class MockImage:
    """
    Mock 图片源：重复返回一张静态图片。
    """

    def __init__(self, frame_path: str) -> None:
        self._frame_path = frame_path
        self._frame = cv2.imread(frame_path)
        self._opened = self._frame is not None

    def read(self, image: cv2.typing.MatLike | None = None) -> tuple[bool, cv2.typing.MatLike | None]:
        return self._opened, self._frame if self._opened else None

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self._frame = None
        self._opened = False


class MockVideo:
    """
    Mock 视频源：循环播放本地视频文件。
    """

    def __init__(self, video_path: str) -> None:
        self.video_path = video_path
        self.video = cv2.VideoCapture(video_path)
        if not self.video.isOpened():
            raise Exception(f"无法打开视频文件: {video_path}")

    def _reload_video(self) -> None:
        self.video.release()
        self.video = cv2.VideoCapture(self.video_path)
        if not self.video.isOpened():
            raise Exception(f"无法打开视频文件: {self.video_path}")

    def read(self, image: cv2.typing.MatLike | None = None) -> tuple[bool, cv2.typing.MatLike | None]:
        ret, frame = self.video.read()
        if ret:
            return True, frame
        else:
            self._reload_video()
            return self.read()

    def isOpened(self) -> bool:
        return self.video.isOpened()

    def release(self) -> None:
        self.video.release()


class InterpolatedCap(Cap):
    """
    运用插值补帧方法的Cap类
    """

    def __init__(self, _id: int|None = None) -> None:
        super().__init__(_id)
        self.set(3, 640)
        self.set(4, 480)
        self.set(5, 100)
        self.set(6, cv2.VideoWriter.fourcc("M", "J", "P", "G"))

        self.prev_frame = None
        # 插值系数
        self.alpha = 0.6
        self.prev_tick = cv2.getTickCount()
        self.frame_count = 0
        # 用于存储最近30帧的FPS值
        self.fps_deque = deque(maxlen=30)
        self.avg_fps = 0
        self.interpolated_frame = None

    def read(self):
        ret, frame = super().read()
        if ret:
            if self.prev_frame is not None:
                # 使用插值方法生成新帧
                self.interpolated_frame = cv2.addWeighted(
                    frame, self.alpha, self.prev_frame, 1 - self.alpha, 0
                )
            self.prev_frame = frame

        if self.interpolated_frame is not None:
            return ret, self.interpolated_frame
        return ret, frame

    def release(self):
        super().release()
        cv2.destroyAllWindows()
