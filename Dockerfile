# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies in smaller batches to reduce memory usage
# Batch 1: Basic utilities
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Batch 2: Font packages
RUN apt-get update && apt-get install -y \
    fonts-liberation \
    fontconfig \
    libfreetype6-dev \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Batch 3: Browser dependencies (part 1)
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    && rm -rf /var/lib/apt/lists/*

# Batch 4: Browser dependencies (part 2)
RUN apt-get update && apt-get install -y \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    && rm -rf /var/lib/apt/lists/*

# Batch 5: Browser dependencies (part 3)
RUN apt-get update && apt-get install -y \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy the Railway-specific environment file
COPY .env.railway .env

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DISPLAY=:99
ENV DISABLE_GIF_CREATION=true
ENV RAILWAY_ENVIRONMENT=production
ENV USE_WEBHOOK=true

# Run the bot
CMD ["python", "main.py"]
