# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and fonts
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    fonts-liberation \
    fontconfig \
    libfreetype6-dev \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DISPLAY=:99
ENV DISABLE_GIF_CREATION=true
ENV RAILWAY_ENVIRONMENT=production

# Run the bot
CMD ["python", "main.py"]
