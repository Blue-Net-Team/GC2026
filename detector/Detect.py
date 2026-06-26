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
from typing import Any, Optional

import cv2
import numpy as np

from utils.ConfigLoader import ConfigLoader


class Detect(ConfigLoader):
    """
    检测器基类
    ----
    提供了两种锐化方法：
    1. usm_sharpen: USM锐化（推荐），效果更自然，可控制参数
    2. sharpen: 拉普拉斯锐化（传统方法），简单快速

    子类可通过 TUNABLE_PARAMS 声明可调参数，并实现 Tunable / Preview 接口：
    - tunable_schema() -> DetectorSchema
    - get_tunable_value(key, section)
    - set_tunable_value(key, value, section)
    - load_tunable_from_app_config(app_config)
    - save_tunable_to_app_config(app_config)
    - async detect(frame) -> (result, binary)
    - draw_overlay(frame, result, binary) -> np.ndarray
    - format_detection_info(result) -> str
    """

    # ------------------------------------------------------------------
    # Tunable 接口（默认实现适合参数平铺在类属性上的 detector）
    # ------------------------------------------------------------------
    @classmethod
    def tunable_schema(cls) -> "DetectorSchema":
        """返回可调参数 schema。默认从 TUNABLE_PARAMS 类属性读取。"""
        return cls.TUNABLE_PARAMS

    def get_tunable_value(self, key: str, section: Optional[str] = None) -> Any:
        """读取单个可调参数的实际值。section 对平铺参数 detector 可忽略。"""
        return getattr(self, key)

    def set_tunable_value(
        self, key: str, value: Any, section: Optional[str] = None
    ) -> None:
        """写入单个可调参数的实际值。section 对平铺参数 detector 可忽略。

        如果参数在 schema 中声明为 int，则自动四舍五入为整数，避免 UI 传回 float 导致 OpenCV 报错。
        """
        param = self.tunable_schema().get_param(key, section)
        if param is not None and param.param_type == "int":
            value = int(round(value))
        setattr(self, key, value)

    def load_tunable_from_app_config(self, app_config: Any) -> None:
        """从 AppConfig 加载所有可调参数。默认实现按 schema 的顶层 key 同步。

        通过 set_tunable_value 写入，确保 int 参数被正确截断为整数。
        """
        schema = self.tunable_schema()
        cfg = getattr(app_config, schema.name, {})
        for param in schema.params:
            key = param.key
            if isinstance(cfg, dict):
                value = cfg.get(key, getattr(self, key))
            else:
                value = getattr(cfg, key, getattr(self, key))
            self.set_tunable_value(key, value)

    def save_tunable_to_app_config(self, app_config: Any) -> None:
        """保存所有可调参数到 AppConfig。默认实现按 schema 的顶层 key 同步。"""
        schema = self.tunable_schema()
        cfg = getattr(app_config, schema.name, {})
        for param in schema.params:
            key = param.key
            value = getattr(self, key)
            if isinstance(cfg, dict):
                cfg[key] = value
            else:
                setattr(cfg, key, value)

    # ------------------------------------------------------------------
    # 预览接口（子类必须实现 detect / draw_overlay / format_detection_info）
    # ------------------------------------------------------------------
    async def detect(self, frame: np.ndarray) -> tuple[Any, np.ndarray]:
        """检测一帧图像，返回 (result, binary)。"""
        raise NotImplementedError

    def draw_overlay(self, frame: np.ndarray, result: Any, binary: np.ndarray) -> np.ndarray:
        """在原图上绘制检测结果，返回上侧预览图。"""
        raise NotImplementedError

    def format_detection_info(self, result: Any) -> str:
        """将检测结果格式化为信息区文本。"""
        raise NotImplementedError

    def visualize(
        self, frame: np.ndarray, result: Any, binary: np.ndarray
    ) -> np.ndarray:
        """默认可视化：上侧 overlay + 下侧 binary，供应用层调用。"""
        overlay = self.draw_overlay(frame, result, binary)
        if binary.ndim == 2:
            binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        else:
            binary_bgr = binary
        return np.vstack([overlay, binary_bgr])

    @staticmethod
    def sharpen(_img):
        """
        拉普拉斯锐化（传统方法）
        ----
        :param _img: 需要锐化的图片
        """
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        img = _img.copy()
        img = cv2.filter2D(img, -1, kernel)
        return img

    @staticmethod
    def usm_sharpen(_img, sigma=5.0, strength=1.5, threshold=0):
        """
        USM锐化（Unsharp Mask锐化）
        ----
        :param _img: 需要锐化的图片
        :param sigma: 高斯模糊的sigma值，控制锐化半径，默认5.0
        :param strength: 锐化强度系数，默认1.5（推荐范围0.5-2.0）
        :param threshold: 阈值，低于此值不锐化，默认0（可选范围0-255）
        :return: 锐化后的图片
        """
        img = _img.copy()
        
        blurred = cv2.GaussianBlur(img, (0, 0), sigma)
        
        sharpened = cv2.addWeighted(img, 1 + strength, blurred, -strength, 0)
        
        if threshold > 0:
            diff = cv2.absdiff(img, blurred)
            mask = diff > threshold
            sharpened = np.where(mask, sharpened, img)

        return sharpened

    def __str__(self):
        """
        返回检测器当前配置参数的字符串表示
        """
        attrs = {}
        for key in dir(self):
            if not key.startswith("_") and not callable(getattr(self, key)):
                attrs[key] = getattr(self, key)
        return f"{self.__class__.__name__}({attrs})"
