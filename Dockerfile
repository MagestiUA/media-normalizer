FROM python:3.11-slim

# Install system dependencies (FFmpeg is crucial)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements if they exist (assuming manual install otherwise)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Since we only use PyYAML, let's just install it
RUN pip install --no-cache-dir pyyaml pydantic

# Copy application code
COPY . .

# Create volume mount points
VOLUME /config
VOLUME /data

# Default environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
