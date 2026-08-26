FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
