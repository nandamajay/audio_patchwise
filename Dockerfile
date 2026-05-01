FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS production

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    patch \
    diffutils \
    perl \
    nginx \
    lsof \
    netcat-openbsd \
    sendmail \
    && rm -rf /var/lib/apt/lists/*

# Download checkpatch.pl
RUN curl -sL https://raw.githubusercontent.com/torvalds/linux/master/scripts/checkpatch.pl \
    -o /usr/local/bin/checkpatch.pl && chmod +x /usr/local/bin/checkpatch.pl

# Download kernel spelling file (required by checkpatch)
RUN curl -sL https://raw.githubusercontent.com/torvalds/linux/master/scripts/spelling.txt \
    -o /usr/local/lib/spelling.txt

# Python dependencies
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

# Copy nginx config
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directories
RUN mkdir -p /app/data/chromadb /app/data/sqlite /app/data/patches /app/logs

EXPOSE 7000

ENTRYPOINT ["/entrypoint.sh"]
