FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY bot.py wizz.py ./

USER 10001:10001
STOPSIGNAL SIGINT
CMD ["python", "bot.py"]
