# Production Dockerfile for CHRONOS Temporal Control Plane
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Expose server port
EXPOSE 8000

# Start FastAPI application with dynamic PORT
CMD uvicorn chronos.server.app:app --host 0.0.0.0 --port ${PORT:-8000}
