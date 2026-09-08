FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DJANGO_BUILD allows collectstatic without a real database.
RUN SECRET_KEY=build-only \
    DJANGO_BUILD=1 \
    python manage.py collectstatic --noinput

RUN sed -i "s/\r$//" /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
