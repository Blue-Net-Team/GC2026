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
import numpy as np

from utils.ConfigLoader import ConfigLoader


class Detect(ConfigLoader):
    """
    检测器基类
    ----
    提供了两种锐化方法：
    1. usm_sharpen: USM锐化（推荐），效果更自然，可控制参数
    2. sharpen: 拉普拉斯锐化（传统方法），简单快速
    """

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
