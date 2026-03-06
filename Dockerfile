FROM python:3.11-slim

WORKDIR /app

# Install system dependencies + fonts
RUN apt-get update && apt-get install -y \
    gcc \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/assets/fonts \
    && cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /app/assets/fonts/ \
    && cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf /app/assets/fonts/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "bot.py"]