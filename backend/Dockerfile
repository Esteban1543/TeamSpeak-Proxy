FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Corre como root para poder escribir en el volumen ./data montado desde el host
# y abrir cualquier puerto del rango configurado (incluidos < 1024 si se desea).
VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
