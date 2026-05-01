#!/bin/bash
set -e

# Replace placeholder with actual port in nginx config
NGINX_PORT=${APP_PORT:-7000}
sed -i "s/__NGINX_PORT__/$NGINX_PORT/g" /etc/nginx/nginx.conf

echo "============================================"
echo "  🔥 PatchWise — CHANAKYA & ARYABHATA"
echo "  Starting on port: $NGINX_PORT"
echo "============================================"

# Start FastAPI backend (internal only on 8000)
echo ">> Starting ARYABHATA backend (FastAPI)..."
cd /app/backend
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
FASTAPI_PID=$!

# Wait for FastAPI to be ready
echo ">> Waiting for backend to be ready..."
for i in $(seq 1 30); do
    if nc -z 127.0.0.1 8000 2>/dev/null; then
        echo ">> Backend is ready!"
        break
    fi
    sleep 1
done

# Start nginx
echo ">> Starting CHANAKYA frontend (nginx)..."
nginx -g "daemon off;" &
NGINX_PID=$!

echo "============================================"
echo "  ✅ PatchWise is running!"
echo "  Open: http://localhost:$NGINX_PORT"
echo "============================================"

# Wait for either process to exit
wait $FASTAPI_PID $NGINX_PID
