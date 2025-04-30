#!/bin/bash

# Проверка на существование виртуального окружения
if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -U -r requirements.txt
else
    echo "Виртуальное окружение уже существует."
    source .venv/bin/activate
fi

# Запуск основного скрипта
python start.py
