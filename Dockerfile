FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV BOT_TOKEN=""
ENV ADMIN_USERNAME=""
ENV ADMIN_USER_ID=""
ENV DATA_DIR="/app/data"

CMD ["python", "bot.py"]