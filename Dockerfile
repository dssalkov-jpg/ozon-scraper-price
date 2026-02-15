FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

WORKDIR /app

# Зависимости для Chromium + Xvfb (виртуальный дисплей)
RUN apt-get update && apt-get install -y \
  xvfb \
  curl \
  ca-certificates \
  fonts-liberation \
  fonts-noto-color-emoji \
  libasound2 \
  libatk-bridge2.0-0 \
  libatk1.0-0 \
  libcups2 \
  libdbus-1-3 \
  libdrm2 \
  libgbm1 \
  libnspr4 \
  libnss3 \
  libx11-6 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxrandr2 \
  libxshmfence1 \
  libxkbcommon0 \
  libgtk-3-0 \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium

COPY . .

EXPOSE 8000

# Запуск uvicorn через xvfb-run
CMD ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24 -nolisten tcp", "uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]
