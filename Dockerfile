FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HOST=0.0.0.0

# Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY . .

# Remove development files
RUN rm -rf venv/ __pycache__/ tests/ docs/ *.save .env.example

# Port
EXPOSE 8080

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
