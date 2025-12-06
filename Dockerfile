FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY iccc/ ./iccc/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "iccc.observability.server:app", "--host", "0.0.0.0", "--port", "8000"]
