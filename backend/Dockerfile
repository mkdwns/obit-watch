FROM python:3.12-slim

# curl_cffi needs these system libs for TLS fingerprinting
RUN apt-get update && apt-get install -y \
    curl \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "main.py"]
