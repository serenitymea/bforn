FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV BOT_TOKEN=""
ENV ADMIN_USERNAME=""
ENV DATA_DIR="/app/data"

CMD ["python", "bot.py"]