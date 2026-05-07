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
import time

import cv2
import numpy as np
import yaml
from colorama import Fore, init

from Solution import Solution
from ImgTrans import ReceiveImg, ReceiveImgTCP, ReceiveImgUDP
from utils import Cap

# 初始化 colorama
init(autoreset=True)


class Ad_Config(Solution):
    """
    调整参数

    * 调整圆环参数，地面
    * 调整直线参数，canny算子参数
    * 调整颜色阈值
    """
    missed_frames:int = 0  # 没有识别到图像的帧数

    def __init__(
        self,
        _cap: cv2.VideoCapture | Cap | ReceiveImg,
        ser_port: str|None = None,
    ):
        super().__init__(ser_port, "config.yaml")

        self.cap = _cap

    def adjust_circle(self):
        """
        调整圆环参数
        ----
        """
        cv2.namedWindow("img", cv2.WINDOW_NORMAL)
        detector = self.annulus_circle_detector

        # 创建滑动条
        detector.createTrackbar()
        while True:
            _, img = self.cap.read()

            if img is None:
                continue

            res, res_img = self.annulus_top(img)

            if res:
                # 计算丢图率
                miss_rate = self.missed_frames / (self.missed_frames + 1)
                timeStamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(
                    Fore.GREEN + f"[{timeStamp}]" + Fore.RESET,
                    Fore.WHITE + f"检测到圆环，圆心坐标：x" + Fore.RESET,
                    Fore.MAGENTA + f"{res[5:8]}" + Fore.RESET,
                    Fore.WHITE + f"y" + Fore.RESET,
                    Fore.MAGENTA + f"{res[8:11]}" + Fore.RESET,
                    Fore.WHITE + f"miss rate" + Fore.RESET,
                    Fore.MAGENTA + f"{miss_rate:.2%}" + Fore.RESET,
                )
            else:
                self.missed_frames += 1

            cv2.imshow("img", res_img)

            press_key = cv2.waitKey(1)
            if press_key & 0xFF == ord("q"):
                # 释放摄像头
                # self.cap.release()
                break
            elif press_key & 0xFF == ord("s"):
                # 保存配置
                detector.save_config("config.yaml")
                print(Fore.GREEN + "保存配置")
        cv2.destroyAllWindows()

    def adjust_color_threshold(self, color_name: str="R"):
        """
        调整颜色阈值
        ----
        """
        self.traditional_color_detector.createTrackbar()
        cv2.namedWindow("img", cv2.WINDOW_NORMAL)
        self.traditional_color_detector.update_range(color_name)
        while True:
            _, img = self.cap.read()
            if img is None:
                continue

            new_img = img.copy()

            binarization_img = self.traditional_color_detector.binarization(img)

            position = self.traditional_color_detector.get_color_position(binarization_img)
            if position:
                point = position[:2]
                w, h = position[2:]

                # 画矩形
                cv2.rectangle(
                    new_img,
                    (point[0] - w // 2, point[1] - h // 2),
                    (point[0] + w // 2, point[1] + h // 2),
                    (0, 255, 0),
                    2,
                )
                # 画出中心点
                cv2.circle(new_img, (point[0], point[1]), 5, (0, 0, 255), -1)

            # 按位与的图
            and_img = cv2.bitwise_and(img, img, mask=binarization_img)

            res_img = np.vstack(
                (new_img, cv2.cvtColor(binarization_img, cv2.COLOR_GRAY2BGR), and_img)
            )

            cv2.imshow("img", res_img)

            key_pressed = cv2.waitKey(1)

            if key_pressed & 0xFF == ord("q"):
                break
            elif key_pressed & 0xFF == ord("s"):
                self.traditional_color_detector.save_config("config.yaml")
                print(Fore.GREEN + "保存配置")

        # self.cap.release()
        cv2.destroyAllWindows()

    def adjust_rightAngle(self):
        """
        调整直角识别参数
        ----
        """
        cv2.namedWindow("img", cv2.WINDOW_NORMAL)
        detector = self.line_detector

        # 创建滑动条
        detector.createTrackbar()
        while True:
            _, img = self.cap.read()

            if img is None:
                continue

            res, res_img = self.right_angle_detect(img)

            if res:
                miss_present = self.missed_frames / (self.missed_frames + 1)
                timeStamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(
                    Fore.GREEN + f"[{timeStamp}]" + Fore.RESET,
                    Fore.WHITE + f"检测到直角，角度：" + Fore.RESET,
                    Fore.MAGENTA + f"{'+' if res[1]=='1' else '-'}{res[2:4]}.{res[4]}\t" + Fore.RESET,
                    Fore.WHITE + f"交点坐标：x:" + Fore.RESET,
                    Fore.MAGENTA + f"{res[5:8]}\t" + Fore.RESET,
                    Fore.WHITE + f"y:" + Fore.RESET,
                    Fore.MAGENTA + f"{res[8:11]}" + Fore.RESET,
                    Fore.WHITE + f"miss present: {miss_present:.2%}" + Fore.RESET,
                )
            else:
                self.missed_frames += 1

            cv2.imshow("img", res_img)

            press_key = cv2.waitKey(1)
            if press_key & 0xFF == ord("q"):
                break
            elif press_key & 0xFF == ord("s"):
                detector.save_config("config.yaml")
                timeStamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                print(
                    Fore.GREEN + f"[{timeStamp}]" + Fore.RESET,
                    Fore.CYAN + "保存配置" + Fore.RESET
                )
        cv2.destroyAllWindows()


class Ad_Area_config:
    """
    调整位号的点位参数
    ----
    * 鼠标左键点击位号的左上角点
    * 鼠标右键点击位号的右下角点
    * 滑动条选择位号
    """
    area_dict: dict[int, list[tuple[int, int]]]
    x:int

    def __init__(self, _cap: cv2.VideoCapture | Cap | ReceiveImg) -> None:
        self.load_config()
        self.x = 0

        self.cap = _cap

    def load_config(self):
        """
        加载配置
        """
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.area_dict = {
            1: self.config["area1_points"],
            2: self.config["area2_points"],
            3: self.config["area3_points"],
        }

    def save_config(self):
        """
        保存配置
        """
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.config["area1_points"] = self.area_dict[1]
        self.config["area2_points"] = self.area_dict[2]
        self.config["area3_points"] = self.area_dict[3]

        with open("config.yaml", "w", encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False)

    def createTrackbar(self):
        cv2.namedWindow("trackbar", cv2.WINDOW_NORMAL)
        cv2.createTrackbar("id", "trackbar", 0, 2, self.__callback)

    def __callback(self, x: int):
        self.x = x

    def __mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.area_dict[self.x + 1][0] = (x, y)
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.area_dict[self.x + 1][1] = (x, y)

    def main(self):
        cv2.namedWindow("img", cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback("img", self.__mouse_callback)
        self.createTrackbar()

        while True:
            _, img = self.cap.read()
            if img is None:
                continue
            for key, value in self.area_dict.items():
                cv2.rectangle(
                    img,
                    value[0],
                    value[1],
                    (0, 255, 0),
                    2
                )
                cv2.putText(
                    img,
                    f"area{key}",
                    # value[0]+(20,20),
                    (value[0][0], value[0][1] + 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1
                )
            cv2.imshow("img", img)
            key = cv2.waitKey(1)
            if key & 0xFF == ord("q"):
                break
            elif key & 0xFF == ord("s"):
                self.save_config()
                print(Fore.GREEN + "保存配置")
        cv2.destroyAllWindows()


def ad_color(_cap: cv2.VideoCapture | Cap | ReceiveImg):
    ad_config = Ad_Config(_cap)
    ad_config.adjust_color_threshold()

def ad_circle(_cap: cv2.VideoCapture | Cap | ReceiveImg):
    ad_config = Ad_Config(_cap)
    ad_config.adjust_circle()

def ad_area(_cap: cv2.VideoCapture | Cap | ReceiveImg):
    ad_area_config = Ad_Area_config(_cap)
    ad_area_config.main()

def ad_right_angle(_cap: cv2.VideoCapture | Cap | ReceiveImg):
    ad_line_config = Ad_Config(_cap)
    ad_line_config.adjust_rightAngle()


if __name__ == "__main__":
    # 机载摄像头
    # cap = Cap(0)

    # 图传接收器
    cap = ReceiveImgUDP("169.254.133.100", 4444, "169.254.233.52")

    #  先s保存，再q退出
    ad_color(cap)
    ad_area(cap)
    ad_circle(cap)
    ad_right_angle(cap)
# end main
