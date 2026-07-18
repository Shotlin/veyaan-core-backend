FROM python:3.12.3-alpine3.19

WORKDIR /app

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    postgresql-dev \
    curl

# Create veyaan group and user with explicit UID/GID
RUN addgroup -g 10001 -S veyaan && \
    adduser -u 10001 -S -G veyaan veyaan && \
    chown -R veyaan:veyaan /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN chown -R veyaan:veyaan /app

USER veyaan

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]