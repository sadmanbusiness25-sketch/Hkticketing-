FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir python-telegram-bot playwright

CMD ["python", "bot.py"]
