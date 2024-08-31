#!/bin/bash

SERVICE_FILE="riverapay.service"

# Копирование нового файла службы
echo "Копирование нового файла службы..."
sudo cp $SERVICE_FILE /etc/systemd/system/

# Перезагрузка демона systemd
echo "Перезагрузка демона systemd..."
sudo systemctl daemon-reload

# Перезапуск службы
echo "Перезапуск службы..."
sudo systemctl stop $SERVICE_FILE
sudo systemctl start $SERVICE_FILE

# Включение службы для автоматического старта
echo "Включение службы для автоматического старта..."
sudo systemctl enable $SERVICE_FILE

# Проверка статуса службы
echo "Проверка статуса службы..."
sudo systemctl status $SERVICE_FILE
