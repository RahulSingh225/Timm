FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for Postgres, PyTorch, and building extensions
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    g++ \
    libc6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install torch with CPU support first (as a build dependency for other packages)
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --no-build-isolation -r requirements.txt

# Copy the rest of the application
COPY . .
EXPOSE 4500
# In docker-compose, we will override the CMD for different micro-services
# But we can set a default worker
CMD ["python", "main.py"]
