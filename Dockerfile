# 1. Берем официальный и легкий образ Python
FROM python:3.10-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Копируем файл зависимостей
COPY requirements.txt .

# 4. Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# 5. Копируем весь остальной код проекта
COPY . .
# 6. Указываем порт
EXPOSE 8000

# 7. Команда запуска сервера
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]