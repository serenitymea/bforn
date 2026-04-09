FROM python:3.11-slim

WORKDIR /app

# psycopg2 вимагає libpq
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV BOT_TOKEN=""
ENV ADMIN_USERNAME=""
ENV ADMIN_USER_ID=""
ENV POSTGRES_HOST="db"
ENV POSTGRES_PORT="5432"
ENV POSTGRES_DB="botdb"
ENV POSTGRES_USER="botuser"
ENV POSTGRES_PASSWORD=""

CMD ["python", "bot.py"]