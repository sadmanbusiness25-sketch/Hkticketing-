FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir python-telegram-bot playwright

CMD ["python", "bot.py"]
