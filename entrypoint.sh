#!/bin/bash
set -e

echo ""
echo "  ██████╗  █████╗ ████████╗ ██████╗██╗  ██╗██╗    ██╗██╗███████╗███████╗"
echo "  ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝██║  ██║██║    ██║██║██╔════╝██╔════╝"
echo "  ██████╔╝███████║   ██║   ██║     ███████║██║ █╗ ██║██║███████╗█████╗  "
echo "  ██╔═══╝ ██╔══██║   ██║   ██║     ██╔══██║██║███╗██║██║╚════██║██╔══╝  "
echo "  ██║     ██║  ██║   ██║   ╚██████╗██║  ██║╚███╔███╔╝██║███████║███████╗"
echo "  ╚═╝     ╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝"
echo ""
echo "  🔍 CHANAKYA (Reviewer)  ⟷  🛠️ ARYABHATA (Developer)"
echo "  Agent-to-Agent Kernel Patch Review System"
echo "  ──────────────────────────────────────────"
echo ""

if [ -f /run/secrets/gerrit_ssh_key ]; then
    echo "🔐 Loading Gerrit SSH key into SSH agent..."
    eval "$(ssh-agent -s)"
    TMP_GERRIT_KEY=/tmp/gerrit_id_rsa
    cp /run/secrets/gerrit_ssh_key "${TMP_GERRIT_KEY}"
    chmod 600 "${TMP_GERRIT_KEY}"
    if ssh-add "${TMP_GERRIT_KEY}"; then
        echo "  ✅ Gerrit SSH key loaded into SSH agent"
    else
        echo "  ⚠️  Gerrit SSH key could not be loaded into SSH agent"
    fi
else
    echo "  ⚠️  No Gerrit SSH key found at /run/secrets/gerrit_ssh_key"
fi

if [ -f /run/secrets/github_token ]; then
    export GITHUB_TOKEN=$(cat /run/secrets/github_token)
    echo "  ✅ GitHub token loaded from secret"
else
    echo "  ⚠️  No GitHub token found at /run/secrets/github_token"
fi

APP_PORT=${APP_PORT:-7000}
sed -i "s/__NGINX_PORT__/${APP_PORT}/g" /etc/nginx/nginx.conf
echo "  ✅ nginx configured on port ${APP_PORT}"

echo "  🚀 Starting ARYABHATA + CHANAKYA backend..."
cd /app/backend
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2 &
BACKEND_PID=$!
echo "  ✅ Backend started (PID: ${BACKEND_PID})"

echo "  ⏳ Waiting for backend..."
for i in {1..30}; do
    if curl -sf http://127.0.0.1:8000/api/health > /dev/null; then
        echo "  ✅ Backend ready"
        break
    fi
    sleep 1
done

echo "  🌐 Starting nginx proxy on port ${APP_PORT}..."
nginx -g 'daemon off;' &
NGINX_PID=$!
echo "  ✅ nginx started (PID: ${NGINX_PID})"
echo ""
echo "  🌐 PatchWise is running at http://localhost:${APP_PORT}"
echo "  🔍 CHANAKYA & ARYABHATA are ready!"
echo ""

wait -n $BACKEND_PID $NGINX_PID
exit $?
