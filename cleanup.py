from utils import LED, OLED_I2C

start_LED = LED("GPIO3-A2")
detecting_LED = LED("GPIO3-A4")
oled = OLED_I2C(2, 0x3c)

start_LED.off()
detecting_LED.off()
oled.clear()