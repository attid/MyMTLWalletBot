#!/bin/bash
source /home/RiveraPay/.venv/bin/activate
hypercorn run:app --bind 0.0.0.0:8000 --log-file /home/RiveraPay/hypercorn.log
