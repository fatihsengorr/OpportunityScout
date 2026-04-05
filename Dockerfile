FROM python:3.12-slim

WORKDIR /opt/opportunity-scout

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data logs exports

# Default command: run daily scan
CMD ["python", "-m", "src.cli", "scan", "--tier", "1"]
