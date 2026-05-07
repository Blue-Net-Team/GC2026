#!/bin/bash
mkdir -p /media/sdcard/code/Engineering-innovation-competition-vision/run_log
rm /media/sdcard/code/Engineering-innovation-competition-vision/run_log/output.log
rm /media/sdcard/code/Engineering-innovation-competition-vision/run_log/error.log
touch /media/sdcard/code/Engineering-innovation-competition-vision/run_log/output.log
touch /media/sdcard/code/Engineering-innovation-competition-vision/run_log/error.log

/media/sdcard/miniconda3/envs/EIC/bin/python /media/sdcard/code/Engineering-innovation-competition-vision/main.py --config_path /media/sdcard/code/Engineering-innovation-competition-vision/config.yaml> /media/sdcard/code/Engineering-innovation-competition-vision/run_log/output.log 2> /media/sdcard/code/Engineering-innovation-competition-vision/run_log/error.log