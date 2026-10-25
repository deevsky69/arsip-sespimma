FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARSIP_DATA_DIR=/data \
    ARSIP_TESSDATA=/opt/tessdata

# Model bahasa OCR (Indonesia + Inggris). Mesin Tesseract-nya sudah tertanam di PyMuPDF;
# yang dipakai hanya file .traineddata, ditautkan ke /opt/tessdata agar tidak bergantung versi paket.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr-ind tesseract-ocr-eng \
    && ln -s "$(dirname "$(find /usr/share/tesseract-ocr -name ind.traineddata | head -n1)")" /opt/tessdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=false ARSIP_DATA_DIR=/tmp/build python manage.py collectstatic --noinput \
    && useradd --create-home --uid 1000 arsip \
    && mkdir -p /data && chown arsip:arsip /data

USER arsip
VOLUME ["/data"]
EXPOSE 8000

# Migrasi dijalankan setiap kali kontainer start (aman diulang).
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120 --access-logfile -"]
