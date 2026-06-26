"""
Copyright (C) 2025 IVEN-CN(He Yunfeng)

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

色环检测器模块
====
提供了一个用于检测地面色环的识别器
核心算法来自工创赛2025西安理工大学方案，通过放大圆环与底色的对比度实现强光抗干扰

ColorRingDetector类
----
继承自 `Detect` 类，实现了色环检测的功能

方法:
    - `createTrackbar(self)`:
        创建用于调整检测参数的滑动条窗口
    - `__callback(self, x)`:
        滑动条回调函数，用于更新检测参数
    - `binarization(self, _img)`:
        对输入图像进行色环检测前的预处理，返回单通道图像
    - `get_circles(self, binary)`:
        在预处理后的图像上运行霍夫圆检测
    - `detect(self, _img)`:
        检测图像中的色环，返回圆心坐标和预处理图像
    - `visualize(self, _img, circles, binary)`:
        在原图上绘制检测圆并拼接二值化图，供调参窗口使用
    - `save_config(self, config_path)`:
        保存当前配置到指定的配置文件中

        参数:
            - `config_path (str)`: 配置文件路径
    - `load_config(self, config)`:
        从指定的配置文件中加载配置

        参数:
            - `config (str|dict)`: 配置文件路径或配置字典
"""

import cv2
import numpy as np
from loguru import logger
from .Detect import Detect

# app 调参 UI 通过该 schema 动态渲染滑条
from .schema import DetectorSchema, ParamDef

_log = logger.bind(module="ColorRingDetector")

class ColorRingDetector(Detect):
    """
    色环识别器
    ----
    * 通过放大圆环与底色的对比度，实现强光抗干扰的色环检测
    * 核心思想：不做颜色分割，只针对圆环和非环底色之间的色彩差进行放大
    * 适用于地面色环定位，能在高强对比度光线（阳光照射一半）情况下稳定识别

    参数说明:
    ----
    预处理参数:
        - erode_iter (int): 腐蚀操作迭代次数，默认2
            * 值越大，图像越暗淡，噪声去除越强，但细节可能丢失
        - dilate_kernel_size (int): 膨胀操作核大小，默认7
            * 值越大，图像越亮，目标区域扩张越明显

    对比度增强参数:
        - clahe_clip_limit (float): CLAHE对比度限制参数，默认5.0
            * 值越大，局部对比度增强越明显，但噪声也会放大
        - clahe_tile_size (int): CLAHE分块大小，默认8
            * 值越大，对比度增强范围越广，但局部细节可能丢失
        - alpha (float): 对比度增强系数，默认4.0
            * 值越大，图像对比度越高，边缘越明显

    形态学与模糊参数:
        - morph_kernel_size (int): 形态学梯度操作核大小，默认5
            * 值越大，提取的边缘越粗
        - gaussian_kernel_size (int): 高斯模糊核大小，默认7
            * 值越大，图像越平滑，噪声越少，但边缘越模糊
        - gaussian_sigma (float): 高斯模糊标准差，默认3.0
            * 值越大，模糊程度越高
        - threshold_value (int): 二值化阈值，默认70
            * 值越大，保留的白色区域越少；值越小，保留的白色区域越多

    霍夫圆检测参数:
        - hough_dp (float): 累加器分辨率与图像分辨率的比值，默认1.5
            * 值越大，检测精度越低，速度越快
        - hough_min_dist (int): 检测到的圆心之间的最小距离，默认50
            * 值越大，圆心距离越远才能被同时检测到
        - hough_param1 (int): Canny边缘检测的高阈值，默认100
            * 值越大，检测到的边缘越少
        - hough_param2 (float): 累加器阈值，默认0.95
            * 值越大，检测条件越严格，误检越少，但可能漏检
        - min_radius (int): 检测圆的最小半径，默认15
        - max_radius (int): 检测圆的最大半径，默认50
        - expected_circles (int): 期望检测的圆数量，默认3
    """

    erode_iter: int = 1  # 腐蚀操作迭代次数
    dilate_kernel_size: int = 5  # 膨胀操作核大小
    clahe_clip_limit: float = 2.0  # CLAHE对比度限制参数
    clahe_tile_size: int = 8  # CLAHE分块大小
    morph_kernel_size: int = 3  # 形态学操作核大小
    gaussian_kernel_size: int = 5  # 高斯模糊核大小
    gaussian_sigma: float = 1.5  # 高斯模糊标准差
    alpha: float = 2.0  # 对比度增强系数
    threshold_value: int = 120  # 二值化阈值
    hough_dp: float = 1.5  # 霍夫圆检测累加器分辨率比
    hough_min_dist: int = 100  # 霍夫圆检测圆心最小间距
    hough_param1: int = 100  # 霍夫圆检测Canny边缘检测高阈值
    hough_param2: float = 100.0  # 霍夫圆检测累加器阈值
    min_radius: int = 80  # 检测圆最小半径
    max_radius: int = 280  # 检测圆最大半径
    expected_circles: int = 5  # 期望检测的圆数量

    # 调参 UI 使用的参数 schema
    TUNABLE_PARAMS = DetectorSchema(
        name="color_ring",
        groups=["预处理", "霍夫检测", "后处理"],
        params=[
            ParamDef("erode_iter", "腐蚀迭代", "int", 0, 10, group="预处理"),
            ParamDef("dilate_kernel_size", "膨胀核大小", "int", 3, 15, step=2, odd_only=True, group="预处理"),
            ParamDef("clahe_clip_limit", "CLAHE 限制", "float", 0.5, 10.0, decimals=1, step=0.1, group="预处理"),
            ParamDef("clahe_tile_size", "CLAHE 网格", "int", 2, 16, group="预处理"),

            ParamDef("hough_dp", "霍夫分辨率", "float", 0.1, 3.0, decimals=1, step=0.1, group="霍夫检测"),
            ParamDef("hough_min_dist", "圆心最小距", "int", 0, 200, group="霍夫检测"),
            ParamDef("hough_param1", "Canny 阈值", "int", 0, 255, group="霍夫检测"),
            ParamDef("hough_param2", "累加器阈值", "int", 1, 255, group="霍夫检测"),
            ParamDef("min_radius", "最小半径", "int", 0, 900, group="霍夫检测"),
            ParamDef("max_radius", "最大半径", "int", 0, 900, group="霍夫检测"),
            ParamDef("expected_circles", "期望圆数", "int", 1, 10, group="霍夫检测"),

            ParamDef("morph_kernel_size", "形态学核", "int", 3, 15, step=2, odd_only=True, group="后处理"),
            ParamDef("gaussian_kernel_size", "高斯核", "int", 3, 15, step=2, odd_only=True, group="后处理"),
            ParamDef("gaussian_sigma", "高斯 sigma", "float", 0.1, 5.0, decimals=1, step=0.1, group="后处理"),
            ParamDef("alpha", "对比度增强", "float", 0.1, 10.0, decimals=1, step=0.1, group="后处理"),
            ParamDef("threshold_value", "二值化阈值", "int", 0, 255, group="后处理"),
        ],
    )

    @property
    def dilate_kernel(self):
        return np.ones((self.dilate_kernel_size, self.dilate_kernel_size), np.uint8)

    @property
    def morph_kernel(self):
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (self.morph_kernel_size, self.morph_kernel_size))

    def __callback(self, x):
        try:
            self.erode_iter = cv2.getTrackbarPos("erode_iter", "Trackbar")
            self.dilate_kernel_size = cv2.getTrackbarPos("dilate_kernel", "Trackbar")
            if self.dilate_kernel_size % 2 == 0:
                self.dilate_kernel_size += 1
                cv2.setTrackbarPos("dilate_kernel", "Trackbar", self.dilate_kernel_size)
            self.clahe_clip_limit = cv2.getTrackbarPos("clahe_clip", "Trackbar") / 10.0
            self.clahe_tile_size = cv2.getTrackbarPos("clahe_tile", "Trackbar")
            self.morph_kernel_size = cv2.getTrackbarPos("morph_kernel", "Trackbar")
            if self.morph_kernel_size % 2 == 0:
                self.morph_kernel_size += 1
                cv2.setTrackbarPos("morph_kernel", "Trackbar", self.morph_kernel_size)
            self.gaussian_kernel_size = cv2.getTrackbarPos("gaussian_kernel", "Trackbar")
            if self.gaussian_kernel_size % 2 == 0:
                self.gaussian_kernel_size += 1
                cv2.setTrackbarPos("gaussian_kernel", "Trackbar", self.gaussian_kernel_size)
            self.gaussian_sigma = cv2.getTrackbarPos("gaussian_sigma", "Trackbar") / 10.0
            self.alpha = cv2.getTrackbarPos("alpha", "Trackbar") / 10.0
            self.threshold_value = cv2.getTrackbarPos("threshold", "Trackbar")
            self.hough_dp = max(1, cv2.getTrackbarPos("hough_dp", "Trackbar")) / 10.0
            self.hough_min_dist = cv2.getTrackbarPos("hough_min_dist", "Trackbar")
            self.hough_param1 = cv2.getTrackbarPos("hough_p1", "Trackbar")
            self.hough_param2 = max(1, cv2.getTrackbarPos("hough_p2", "Trackbar"))
            self.min_radius = cv2.getTrackbarPos("min_radius", "Trackbar")
            self.max_radius = cv2.getTrackbarPos("max_radius", "Trackbar")
            self.expected_circles = cv2.getTrackbarPos("expected_circles", "Trackbar")
        except:
            pass

    def createTrackbar(self):
        cv2.namedWindow("Trackbar", cv2.WINDOW_NORMAL)
        cv2.createTrackbar("erode_iter", "Trackbar", self.erode_iter, 10, self.__callback)
        cv2.createTrackbar("dilate_kernel", "Trackbar", self.dilate_kernel_size, 15, self.__callback)
        cv2.createTrackbar("clahe_clip", "Trackbar", int(self.clahe_clip_limit * 10), 100, self.__callback)
        cv2.createTrackbar("clahe_tile", "Trackbar", self.clahe_tile_size, 16, self.__callback)
        cv2.createTrackbar("morph_kernel", "Trackbar", self.morph_kernel_size, 15, self.__callback)
        cv2.createTrackbar("gaussian_kernel", "Trackbar", self.gaussian_kernel_size, 15, self.__callback)
        cv2.createTrackbar("gaussian_sigma", "Trackbar", int(self.gaussian_sigma * 10), 50, self.__callback)
        cv2.createTrackbar("alpha", "Trackbar", int(self.alpha * 10), 100, self.__callback)
        cv2.createTrackbar("threshold", "Trackbar", self.threshold_value, 255, self.__callback)
        cv2.createTrackbar("hough_dp", "Trackbar", int(self.hough_dp * 10), 30, self.__callback)
        cv2.createTrackbar("hough_min_dist", "Trackbar", self.hough_min_dist, 200, self.__callback)
        cv2.createTrackbar("hough_p1", "Trackbar", self.hough_param1, 255, self.__callback)
        cv2.createTrackbar("hough_p2", "Trackbar", int(self.hough_param2), 255, self.__callback)
        cv2.createTrackbar("min_radius", "Trackbar", self.min_radius, 900, self.__callback)
        cv2.createTrackbar("max_radius", "Trackbar", self.max_radius, 900, self.__callback)
        cv2.createTrackbar("expected_circles", "Trackbar", self.expected_circles, 10, self.__callback)

        cv2.setTrackbarPos("erode_iter", "Trackbar", self.erode_iter)
        cv2.setTrackbarPos("dilate_kernel", "Trackbar", self.dilate_kernel_size)
        cv2.setTrackbarPos("clahe_clip", "Trackbar", int(self.clahe_clip_limit * 10))
        cv2.setTrackbarPos("clahe_tile", "Trackbar", self.clahe_tile_size)
        cv2.setTrackbarPos("morph_kernel", "Trackbar", self.morph_kernel_size)
        cv2.setTrackbarPos("gaussian_kernel", "Trackbar", self.gaussian_kernel_size)
        cv2.setTrackbarPos("gaussian_sigma", "Trackbar", int(self.gaussian_sigma * 10))
        cv2.setTrackbarPos("alpha", "Trackbar", int(self.alpha * 10))
        cv2.setTrackbarPos("threshold", "Trackbar", self.threshold_value)
        cv2.setTrackbarPos("hough_dp", "Trackbar", int(self.hough_dp * 10))
        cv2.setTrackbarPos("hough_min_dist", "Trackbar", self.hough_min_dist)
        cv2.setTrackbarPos("hough_p1", "Trackbar", self.hough_param1)
        cv2.setTrackbarPos("hough_p2", "Trackbar", int(self.hough_param2))
        cv2.setTrackbarPos("min_radius", "Trackbar", self.min_radius)
        cv2.setTrackbarPos("max_radius", "Trackbar", self.max_radius)
        cv2.setTrackbarPos("expected_circles", "Trackbar", self.expected_circles)

    async def binarization(self, _img: cv2.typing.MatLike) -> cv2.typing.MatLike:
        """
        色环二值化
        ----
        对输入图像进行腐蚀、膨胀、CLAHE、形态学梯度、高斯模糊、对比度增强、
        二值化、最终模糊等预处理，返回用于霍夫圆检测的单通道图像。

        :param _img: 需要处理的图片
        :return: 预处理后的单通道图像（灰度/二值化图）
        """
        img = _img.copy()

        eroded = cv2.erode(img, None, iterations=self.erode_iter)
        dilated = cv2.dilate(eroded, self.dilate_kernel, iterations=1)

        gray = cv2.cvtColor(dilated, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=(self.clahe_tile_size, self.clahe_tile_size)
        )
        clahe.apply(gray)

        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, self.morph_kernel)

        blurred1 = cv2.GaussianBlur(
            gradient,
            (self.gaussian_kernel_size, self.gaussian_kernel_size),
            self.gaussian_sigma
        )

        scaled = cv2.convertScaleAbs(blurred1, alpha=self.alpha, beta=0)

        blurred2 = cv2.GaussianBlur(
            scaled,
            (self.gaussian_kernel_size, self.gaussian_kernel_size),
            self.gaussian_sigma
        )

        _, binary = cv2.threshold(blurred2, self.threshold_value, 255, cv2.THRESH_BINARY)

        blurred3 = cv2.GaussianBlur(
            binary,
            (self.gaussian_kernel_size + 2, self.gaussian_kernel_size + 2),
            self.gaussian_sigma
        )

        return blurred3

    async def get_circles(
        self, binary: cv2.typing.MatLike
    ) -> list[tuple[int, int, int]] | None:
        """
        霍夫圆检测
        ----
        在 binarization() 返回的单通道图像上运行霍夫圆检测。

        :param binary: 二值化/预处理后的单通道图像
        :return: 检测到的圆列表 [(x, y, r), ...]，未检测到返回 None
        """
        circles = cv2.HoughCircles(
            binary,
            cv2.HOUGH_GRADIENT,
            self.hough_dp,
            self.hough_min_dist,
            param1=self.hough_param1,
            param2=self.hough_param2,
            minRadius=self.min_radius,
            maxRadius=self.max_radius
        )

        if circles is None:
            return None

        circles = np.uint16(np.around(circles))
        circle_list = sorted(circles[0], key=lambda x: x[2], reverse=True)
        return [(int(x), int(y), int(r)) for x, y, r in circle_list]

    async def detect(
        self, _img: cv2.typing.MatLike
    ) -> tuple[list[tuple[int, int, int]] | None, cv2.typing.MatLike]:
        """
        检测色环
        ----
        组合 binarization() 与 get_circles()，返回完整圆列表和预处理图像。
        不在原图上绘制任何标记，由调用方决定如何可视化。

        :param _img: 需要检测的图片
        :return: (圆列表 [(x, y, r), ...], 预处理后的单通道图像)
                 未检测到圆时第一个元素为 None
        """
        binary = await self.binarization(_img)
        circles = await self.get_circles(binary)
        return circles, binary

    def draw_overlay(
        self,
        frame: cv2.typing.MatLike,
        result: list[tuple[int, int, int]] | None,
        binary: cv2.typing.MatLike,
    ) -> cv2.typing.MatLike:
        """
        在原图上绘制检测到的色环和圆心。

        :param frame: 原始图像
        :param result: detect() 返回的圆列表 [(x, y, r), ...]
        :param binary: 预处理后的单通道图像（本方法中未使用，仅保持接口一致）
        :return: 绘制后的图像
        """
        output = frame.copy()
        if result is not None:
            for x, y, r in result:
                cv2.circle(output, (int(x), int(y)), int(r), (0, 0, 255), 2)
                cv2.circle(output, (int(x), int(y)), 2, (255, 0, 0), 2)
        return output

    def format_detection_info(self, result: list[tuple[int, int, int]] | None) -> str:
        """格式化检测信息文本。"""
        if result is None:
            return "未检测到圆"
        lines = [f"检测到 {len(result)} 个圆:"]
        for i, (x, y, r) in enumerate(result[:5], 1):
            lines.append(f"  圆{i}: 中心({x}, {y}) 半径{r}")
        if len(result) > 5:
            lines.append(f"  ... 还有 {len(result) - 5} 个")
        return "\n".join(lines)

    def visualize(
        self,
        _img: cv2.typing.MatLike,
        circles: list[tuple[int, int, int]] | None = None,
        binary: cv2.typing.MatLike | None = None,
    ) -> cv2.typing.MatLike:
        """
        可视化色环检测结果
        ----
        在原图上绘制检测圆，并与二值化图纵向拼接。供独立调参窗口使用。

        :param _img: 原始图像
        :param circles: 检测到的圆列表 [(x, y, r), ...]，为 None 时不画圆
        :param binary: 预处理后的单通道图像，为 None 时使用全黑占位图
        :return: 拼接后的可视化图像
        """
        output = _img.copy()
        if circles is not None:
            for x, y, r in circles:
                cv2.circle(output, (int(x), int(y)), int(r), (0, 0, 255), 2)
                cv2.circle(output, (int(x), int(y)), 2, (255, 0, 0), 2)

        if binary is None:
            binary = np.zeros((_img.shape[0], _img.shape[1]), dtype=np.uint8)

        vis_binary = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return np.vstack([output, vis_binary])

    def save_config(self, config_path: str):
        """
        保存配置
        ----
        Args:
            config_path (str): 保存路径
        """
        circle_type = "color_ring"
        config = super().load_config(config_path)

        config[circle_type] = {
            "erode_iter": self.erode_iter,
            "dilate_kernel_size": self.dilate_kernel_size,
            "clahe_clip_limit": self.clahe_clip_limit,
            "clahe_tile_size": self.clahe_tile_size,
            "morph_kernel_size": self.morph_kernel_size,
            "gaussian_kernel_size": self.gaussian_kernel_size,
            "gaussian_sigma": self.gaussian_sigma,
            "alpha": self.alpha,
            "threshold_value": self.threshold_value,
            "hough_dp": self.hough_dp,
            "hough_min_dist": self.hough_min_dist,
            "hough_param1": self.hough_param1,
            "hough_param2": self.hough_param2,
            "min_radius": self.min_radius,
            "max_radius": self.max_radius,
            "expected_circles": self.expected_circles,
        }

        super().save_config(config_path, config)

    def load_config(self, config: str | dict):
        """
        加载配置
        ----
        Args:
            config(str|dict): 配置文件信息
        Return:
            res_str(str): 错误信息
        """
        circle_type = "color_ring"

        config_dict = {}
        try:
            config_dict = super().load_config(config)
            config_dict = config_dict[circle_type]
        except KeyError:
            _log.warning(f"配置文件 {config} 中没有 {circle_type} 的配置项")
            pass

        super().load_param(config_dict, "erode_iter", default=getattr(type(self), "erode_iter"))
        super().load_param(config_dict, "dilate_kernel_size", default=getattr(type(self), "dilate_kernel_size"))
        super().load_param(config_dict, "clahe_clip_limit", default=getattr(type(self), "clahe_clip_limit"))
        super().load_param(config_dict, "clahe_tile_size", default=getattr(type(self), "clahe_tile_size"))
        super().load_param(config_dict, "morph_kernel_size", default=getattr(type(self), "morph_kernel_size"))
        super().load_param(config_dict, "gaussian_kernel_size", default=getattr(type(self), "gaussian_kernel_size"))
        super().load_param(config_dict, "gaussian_sigma", default=getattr(type(self), "gaussian_sigma"))
        super().load_param(config_dict, "alpha", default=getattr(type(self), "alpha"))
        super().load_param(config_dict, "threshold_value", default=getattr(type(self), "threshold_value"))
        super().load_param(config_dict, "hough_dp", default=getattr(type(self), "hough_dp"))
        super().load_param(config_dict, "hough_min_dist", default=getattr(type(self), "hough_min_dist"))
        super().load_param(config_dict, "hough_param1", default=getattr(type(self), "hough_param1"))
        super().load_param(config_dict, "hough_param2", default=getattr(type(self), "hough_param2"))
        super().load_param(config_dict, "min_radius", default=getattr(type(self), "min_radius"))
        super().load_param(config_dict, "max_radius", default=getattr(type(self), "max_radius"))
        super().load_param(config_dict, "expected_circles", default=getattr(type(self), "expected_circles"))
