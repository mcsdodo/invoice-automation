FROM python:3.12-slim

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY src/ ./src/

# Create data directories
RUN mkdir -p /app/data/incoming /app/data/archive /app/data/temp

CMD ["python", "-m", "src.main"]
