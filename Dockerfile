FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    patch \
    diffutils \
    perl \
    make \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ .

# Copy checkpatch.pl for PatchWise skill
RUN curl -o /usr/local/bin/checkpatch.pl \
    https://raw.githubusercontent.com/torvalds/linux/master/scripts/checkpatch.pl && \
    chmod +x /usr/local/bin/checkpatch.pl

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
