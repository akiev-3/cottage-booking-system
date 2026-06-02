#!/bin/bash
echo "Останавливаем старый процесс на порту 5000..."
lsof -ti :5000 | xargs kill -9 2>/dev/null
sleep 0.5
echo "Запускаем сервер..."
cd "$(dirname "$0")"
env/bin/python app.py
