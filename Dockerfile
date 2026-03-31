FROM python:3.13-slim
LABEL maintainer="s.merlenko@gmail.com"

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/media /app/celerybeat

RUN adduser \
    --disabled-password \
    --no-create-home \
    django-user

RUN chown -R django-user:django-user /app/celerybeat
RUN chmod -R 755 /app/celerybeat

USER django-user
