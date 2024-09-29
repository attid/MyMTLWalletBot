#!/bin/bash

cd /home/mmwb_bot/
source /home/mmwb_bot/.venv/bin/activate
export ENVIRONMENT=production
python3 start.py mmwb_bot

deactivate

