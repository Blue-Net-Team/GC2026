#!/bin/bash
/media/sdcard/miniconda3/envs/EIC/bin/python /media/sdcard/code/Engineering-innovation-competition-vision/cleanup.py> /media/sdcard/code/Engineering-innovation-competition-vision/run_log/output-cleanup.log 2> /media/sdcard/code/Engineering-innovation-competition-vision/run_log/error-cleanup.log
if [ $? -eq 0 ]; then
  echo "成功清理引脚资源"
else
  echo "发生错误"
  cat /media/sdcard/code/Engineering-innovation-competition-vision/run_log/error-cleanup.log
fi