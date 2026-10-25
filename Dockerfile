FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser
COPY app ./app
# No network fetch for fonts at Docker build time.
# Optional: python3 scripts/install_font.py on the host before docker compose build.
# If a verified local app/static/fonts/Vazirmatn.woff2 exists, COPY app includes it.
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--workers", "1"]
