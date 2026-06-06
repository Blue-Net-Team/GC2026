#!/bin/bash

echo "none" |  tee /sys/class/leds/rgb-led-b/trigger
echo "none" |  tee /sys/class/leds/rgb-led-g/trigger
echo "none" |  tee /sys/class/leds/rgb-led-r/trigger
# echo "255" |  tee /sys/class/leds/rgb-led-r/brightness
# echo "timer" |  tee /sys/class/leds/rgb-led-g/trigger

# 以--·--的形式亮绿灯
while true
do
for i in `seq 1 2`
do
    echo "255" |  tee /sys/class/leds/rgb-led-g/brightness
    sleep 0.05
    echo "0" |  tee /sys/class/leds/rgb-led-g/brightness
    sleep 0.05
done
echo "255" |  tee /sys/class/leds/rgb-led-g/brightness
sleep 0.2
echo "0" |  tee /sys/class/leds/rgb-led-g/brightness
sleep 0.2
done
