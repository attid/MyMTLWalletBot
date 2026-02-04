#!/bin/bash

# Переходим в директорию бота
cd "$(dirname "$0")"

# Запуск основного скрипта через uv
uv run python start.py
