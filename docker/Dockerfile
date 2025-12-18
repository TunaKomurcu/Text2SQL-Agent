FROM python:3.11-slim

# Install system deps needed for some packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       git \
       wget \
       ca-certificates \
       libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better cache
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy project
COPY . /app

# Ensure models dir exists (user can mount it)
RUN mkdir -p /app/models

# Entrypoint (now in docker/ folder)
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
