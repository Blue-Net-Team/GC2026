import cv2

from detector import TraditionalColorDetector, ColorRingDetector
from loguru import logger

_log = logger.bind(module="Applications")

class Applications:
    """
    应用类
    """
    def __init__(self, config_path: str):
        _log.info("初始化应用类")
        _log.info(f"配置文件路径: {config_path}")
        self.colorDetector: TraditionalColorDetector = TraditionalColorDetector()
        self.colorRingDetector: ColorRingDetector = ColorRingDetector()
        
        # 颜色检测器配置
        self.colorDetector.load_config(config_path)
        _log.info(f"颜色检测器配置: {self.colorDetector}")
        # 圆检测器配置
        self.colorRingDetector.load_config(config_path)
        _log.info(f"圆检测器配置: {self.colorRingDetector}")
        
    async def detect_material(self, img: cv2.typing.MatLike, color_label: str):
        """
        检测图片中的物料位置
        ----
        :param img: 输入图片
        :param color_label: 颜色标签,包含['R','G','B']
        :return: 物料位置的坐标（x, y）, 处理后的图像（绘制轮廓）
        """
        # 颜色过滤
        self.colorDetector.update_range(color_label)        # 更新颜色范围
        filtered_img = await self.colorDetector.binarization(img)
        # 面积排序
        contours, _ = cv2.findContours(filtered_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
        
        # 取最大面积
        max_contour = contours[0]
        # 色块中心点
        center = cv2.moments(max_contour)
        
        # 绘制轮廓
        draw_img = cv2.cvtColor(filtered_img, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(draw_img, [max_contour], -1, (0, 255, 0), 2)
        
        if center["m00"] == 0:
            _log.warning("未检测到物料中心点")
            return None, draw_img
        
        _log.info(f"检测到物料中心点: {center}")
        return (center["m10"] / center["m00"], center["m01"] / center["m00"]), draw_img
        
    async def detect_circle(self, img: cv2.typing.MatLike, label=None):
        """
        检测图片中的圆位置
        """
        # 圆检测
        res, res_img = await self.colorRingDetector.detect(img)
        if res:
            _log.info(f"检测到圆位置: {res[0]}")
            return res[0], res_img
        else:
            _log.warning("未检测到圆位置")
            return None, res_img
    
    def tuple2str(self, _tuple: tuple|None) -> str:
        """
        元组转换为特定格式的字符串
        格式规则：
        + -> 1, - -> 0，后续数字保持正常，3位数补满
        示例：(12, -115) -> 10120115
        """
        if _tuple is None:
            return 'FFFFFFFF'
        
        x, y = _tuple
        
        # 转换x坐标
        if x >= 0:
            x_sign = '1'
        else:
            x_sign = '0'
        x_abs = int(abs(x))
        x_str = f"{x_sign}{x_abs:03d}"
        
        # 转换y坐标
        if y >= 0:
            y_sign = '1'
        else:
            y_sign = '0'
        y_abs = int(abs(y))
        y_str = f"{y_sign}{y_abs:03d}"
        
        # 组合结果
        res = x_str + y_str
        _log.info(f"转换后的字符串: {res}")
        return res
       
