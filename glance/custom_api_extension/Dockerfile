FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies first for better layer caching
COPY glance/custom_api_extension/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the whole glance package so imports like glance.custom_api_extension work
COPY glance /app/glance

EXPOSE 5001

CMD ["python", "-m", "glance.custom_api_extension.host_flask"]
