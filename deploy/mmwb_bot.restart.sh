#!/bin/bash

SERVICE_FILE="mmwb_bot.service"

# Перезапуск службы
echo "Перезапуск службы..."
sudo systemctl stop $SERVICE_FILE
sudo systemctl start $SERVICE_FILE

# Проверка статуса службы
echo "Проверка статуса службы..."
sudo systemctl status $SERVICE_FILE
