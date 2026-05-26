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
import asyncio
import jieba
from loguru import logger
jieba.lcut("初始化分词器")
_log = logger.bind(module="gpio")

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import sh1106
    from PIL import ImageFont, ImageDraw, Image

    def check_raspberry_pi():
        """检查是否为树莓派"""
        try:
            with open('/proc/device-tree/model', 'r') as file:
                model = file.read().strip()
                _log.info(f"设备型号: {model}")
                if "Raspberry Pi" in model:
                    return True
                else:
                    return False
        except FileNotFoundError:
            _log.error("无法访问设备树信息")
            return False
        except Exception as e:
            _log.error(f"发生错误: {str(e)}")
            return False

    if check_raspberry_pi():
        import RPi.GPIO as GPIO

        # 设置GPIO模式为BCM
        GPIO.setmode(GPIO.BCM)

        class LED:
            def __init__(self, _OutPin: str) -> None:
                """
                初始化LED
                ----
                Args:
                    _OutPin: 输出引脚(BCM编号)，该类会将这个引脚设置为输出模式
                """
                self.OutPin = int(_OutPin)
                GPIO.setup(self.OutPin, GPIO.OUT)

            async def on(self):
                """开启LED"""
                _log.info(f"已开启引脚 {self.OutPin}")
                GPIO.output(self.OutPin, GPIO.HIGH)

            async def off(self):
                """关闭LED"""
                _log.info(f"已关闭引脚 {self.OutPin}")
                GPIO.output(self.OutPin, GPIO.LOW)

        class Switch:
            """开关类"""

            status: bool = False
            readFlag: bool = True

            def __init__(
                self,
                _InPin: str,
                pull_up_down: int = 22,
                _PowPin: int | None = None,
                reverse: bool = False
            ) -> None:
                """
                初始化开关
                ----
                Args:
                    _InPin: 输入引脚，该类回读取这个引脚的电平作为开关状态
                    pull_up_down: 上下拉电阻
                    _PowPin: 电源引脚,设置了的话,将会在初始化时将其设置为高电平
                    reverse: 是否反转开关状态
                """
                self.InPin = int(_InPin)
                self.PowPin = _PowPin
                self.reverse = reverse

                # 设置输入引脚
                GPIO.setup(self.InPin, GPIO.IN, pull_up_down=pull_up_down)

                # 设置电源引脚
                if self.PowPin:
                    GPIO.setup(self.PowPin, GPIO.OUT)
                    _log.info(f"已设置引脚 {self.PowPin} 为输出模式")
                    GPIO.output(self.PowPin, GPIO.HIGH)
                    _log.info(f"已设置引脚 {self.PowPin} 为高电平")

            async def read_status(self) -> bool:
                """
                读取开关状态
                ----
                Returns:
                    status: 开关状态
                """
                self.status = GPIO.input(self.InPin)
                _log.info(f"开关状态: {self.status}")
                return self.status if not self.reverse else not self.status

            def __del__(self) -> None:
                """析构函数"""
                GPIO.cleanup(self.InPin)
                if self.PowPin:
                    GPIO.cleanup(self.PowPin)
    else:
        from periphery import GPIO

        def get_line_id(str_id:str):
            """
            从端口索引号得到总线id
            ----
            Args:
                str_id(str): 端口索引号,如"B1"
            """
            port = str_id[0]
            port_id = {
                "A": 0,
                "B": 1,
                "C": 2,
                "D": 3
            }[port]
            pin = int(str_id[1])
            return port_id*8 + pin

        class LED:
            def __init__(self, str_pin:str) -> None:
                """
                初始化LED
                ----
                Args:
                    str_pin(str): 端口索引号,如"GPIO1-A2"
                """
                self.chip = {
                    "GPIO0": "/dev/gpiochip0",
                    "GPIO1": "/dev/gpiochip1",
                    "GPIO2": "/dev/gpiochip2",
                    "GPIO3": "/dev/gpiochip3",
                    "GPIO4": "/dev/gpiochip4",
                }[str_pin.split("-")[0]]
                self.line = get_line_id(str_pin.split("-")[1])

                self.led = GPIO(self.chip, self.line, "out")

            async def on(self):
                """开启LED"""
                self.led.write(True)

            async def off(self):
                """关闭LED"""
                self.led.write(False)

            def close(self):
                """关闭LED"""
                self.led.write(False)
                self.led.close()

            def __del__(self):
                """析构函数"""
                self.close()


        class Switch:
            """开关类 - 适用于非树莓派设备"""

            status: bool = False
            readFlag: bool = True

            def __init__(
                self,
                str_pin: str,
                reverse: bool = False
            ) -> None:
                """
                初始化开关
                ----
                泰山派只能设置为下拉电阻

                Args:
                    str_pin: 端口索引号，如"GPIO1-A2"
                    reverse: 是否反转开关状态
                """
                self.chip = {
                    "GPIO0": "/dev/gpiochip0",
                    "GPIO1": "/dev/gpiochip1",
                    "GPIO2": "/dev/gpiochip2",
                    "GPIO3": "/dev/gpiochip3",
                    "GPIO4": "/dev/gpiochip4",
                }[str_pin.split("-")[0]]

                self.line = get_line_id(str_pin.split("-")[1])
                self.reverse = reverse

                # 设置输入引脚和上下拉
                self.switch = GPIO(self.chip, self.line, "in")

            async def read_status(self) -> bool:
                """
                读取开关状态
                ----
                Returns:
                    status: 开关状态
                """
                self.status = self.switch.read()
                return self.status if not self.reverse else not self.status

            def __del__(self) -> None:
                """析构函数"""
                self.switch.close()


    class OLED_I2C:
        def __init__(self, port:int=1, add:int=0x3c, lang:str="zh-cn") -> None:
            """
            OLED初始化
            ----
            Args:
                port(int):i2c的总线编号，即i2cdetect -y 1的1
                add(int):16进制的i2c地址
                lang(str):语言,默认为zh-cn,可以改为us-en
            """
            self.Opened = False

            try:
                ser = i2c(port=port, address=add)
                self.device = sh1106(ser)
                # 创建一个空白图像
                self.image = Image.new('1', (self.device.width, self.device.height))
                self.draw = ImageDraw.Draw(self.image)
                self.step = ' '
                if lang == "zh-cn":
                    self._font = ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 12)
                    self.step = ''
                elif lang == "us-en":
                    self._font = ImageFont.load_default()
                else:
                    raise ValueError("不支持的语言")
                self.Opened = True
            except:
                self.Opened = False

        def _sync_text(self, data: str, position: tuple[int, int]):
            """同步版本：在画面中绘制文字，并自动换行（支持换行符）"""
            if not self.Opened:
                return

            x, y = position
            max_width = self.device.width  # 自动获取 OLED 的宽度

            # 按换行符拆分段落
            paragraphs = data.split('\n')

            # 获取字体的 ascent 和 descent
            ascent, descent = self._font.getmetrics()

            for paragraph in paragraphs:
                lines = []
                words = jieba.lcut(paragraph)  # 使用结巴分词进行中文分词
                current_line = ''

                for word in words:
                    # 检查当前行加上新单词是否超出最大宽度
                    test_line = current_line + self.step + word if current_line else word
                    test_width = self.draw.textlength(test_line, font=self._font)

                    if test_width <= max_width:
                        current_line = test_line
                    else:
                        # 如果超出宽度，则将当前行添加到 lines 中，并开始新的一行
                        lines.append(current_line)
                        current_line = word

                # 添加最后一行
                if current_line:
                    lines.append(current_line)

                # 绘制每一行
                for line in lines:
                    # 在每行的最左侧增加 1px 的空白
                    self.draw.text((x + 1, y), line, font=self._font, fill=255)
                    # 计算行高：ascent + descent + 额外的行间距（例如 2 像素）
                    line_height = ascent + descent + 2
                    y += line_height  # 移动到下一行

        async def text(self, data: str, position: tuple[int, int]):
            """
            在画面中绘制文字，并自动换行（支持换行符）
            ----
            Args:
                data(str):需要绘制的文字数据（可以包含换行符）
                position(tuple[int,int]):绘制文字的起始位置
            """
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._sync_text, data, position)

        def _sync_display(self, reverse: bool = False):
            """
            同步版本：在屏幕上显示画面
            ----
            Args:
                reverse(bool):是否旋转180度
            """
            if self.Opened:
                if reverse:
                    self.image = self.image.rotate(180)
                self.device.display(self.image)

        async def display(self, reverse: bool = False):
            """
            在屏幕上显示画面
            ----
            Args:
                reverse(bool):是否旋转180度
            """
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._sync_display, reverse)

        async def clear(self):
            """清空画面"""
            if self.Opened:
                self.draw.rectangle(self.device.bounding_box, fill="black")
except:
    _log.error("无法使用GPIO相关的库")

    class LED :
        def __init__(self, _OutPin: int) -> None:
            pass

        async def on(self):
            pass

        async def off(self):
            pass

    class Switch:
        status: bool = False
        readFlag: bool = True

        def __init__(
            self,
            _InPin: int,
            pull_up_down: int = 22,
            _PowPin: int | None = None,
            reverse: bool = False
        ) -> None:
            pass

        async def read_status(self) -> bool:
            return False

    class OLED_I2C:
        def __init__(self, port:int=1, add:int=0x3c) -> None:
            pass

        async def text(self, data:str, position:tuple[int, int]):
            pass

        async def display(self):
            pass

        async def clear(self):
            pass
