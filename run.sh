#!/bin/bash

# ============================================================
#   PatchWise — run.sh
#   CHANAKYA (Reviewer) ⟷ ARYABHATA (Developer)
#   Autonomous A2A Patch Review System
# ============================================================

set -e

IMAGE_NAME="patchwise"
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
ENV_EXAMPLE=".env.example"
DEFAULT_PORT=7000

# ── ASCII Banner ─────────────────────────────────────────────
print_banner() {
    echo ""
    echo "  ██████╗  █████╗ ████████╗ ██████╗██╗  ██╗██╗    ██╗██╗███████╗███████╗"
    echo "  ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝██║  ██║██║    ██║██║██╔════╝██╔════╝"
    echo "  ██████╔╝███████║   ██║   ██║     ███████║██║ █╗ ██║██║███████╗█████╗  "
    echo "  ██╔═══╝ ██╔══██║   ██║   ██║     ██╔══██║██║███╗██║██║╚════██║██╔══╝  "
    echo "  ██║     ██║  ██║   ██║   ╚██████╗██║  ██║╚███╔███╔╝██║███████║███████╗"
    echo "  ╚═╝     ╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝"
    echo ""
    echo "        🔍 CHANAKYA (Reviewer)  ⟷  🛠️  ARYABHATA (Developer)"
    echo "             Autonomous A2A Kernel Patch Review System"
    echo ""
}

# ── Dynamic Port Finder (AKDW pattern) ───────────────────────
find_free_port() {
    local port=$1
    while lsof -iTCP:$port -sTCP:LISTEN &>/dev/null 2>&1; do
        echo ">> Port $port is busy, trying $((port+1))..." >&2
        port=$((port+1))
    done
    echo $port
}

# ── Setup .env ───────────────────────────────────────────────
setup_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo ">> .env not found. Creating from .env.example..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo ">> Please review .env."
        echo ">> For highest-accuracy mode set LLM_PROVIDER=qgenie and provide QGENIE_API_KEY."
        echo ">> OpenAI/Anthropic can be used as fallback."
        echo ">> Then run: ./run.sh start"
        exit 0
    fi
    source "$ENV_FILE"
}

upsert_env_value() {
    local key="$1"
    local value="$2"
    local tmp_file="${ENV_FILE}.tmp"
    awk -v key="$key" -v value="$value" '
        BEGIN { found = 0 }
        $0 ~ "^" key "=" {
            print key "=" value
            found = 1
            next
        }
        { print }
        END {
            if (!found) {
                print key "=" value
            }
        }
    ' "$ENV_FILE" > "$tmp_file"
    mv "$tmp_file" "$ENV_FILE"
}

provider_key_var() {
    local provider="$1"
    case "$provider" in
        qgenie) echo "QGENIE_API_KEY" ;;
        openai) echo "OPENAI_API_KEY" ;;
        anthropic) echo "ANTHROPIC_API_KEY" ;;
        qualcomm) echo "QUALCOMM_API_KEY" ;;
        *) echo "" ;;
    esac
}

provider_requires_key() {
    local provider="$1"
    case "$provider" in
        qgenie|openai|anthropic|qualcomm) return 0 ;;
        *) return 1 ;;
    esac
}

is_placeholder_key() {
    local value="${1:-}"
    value="$(echo "$value" | tr '[:upper:]' '[:lower:]')"
    case "$value" in
        ""|"your-qgenie-api-key-here"|"your-openai-key-here"|"your-anthropic-key-here"|"your_api_key_here")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

prompt_for_missing_llm_key() {
    local provider="${LLM_PROVIDER:-qgenie}"
    provider="${provider%%/*}"
    provider="${provider%%:*}"
    provider="$(echo "$provider" | tr '[:upper:]' '[:lower:]')"

    if [ "$provider" = "qualcomm" ]; then
        provider="qgenie"
    fi

    if ! provider_requires_key "$provider"; then
        return
    fi

    local key_var
    key_var="$(provider_key_var "$provider")"
    local provider_key="${!key_var}"
    local generic_key="${LLM_API_KEY:-}"
    if ! is_placeholder_key "$provider_key" || ! is_placeholder_key "$generic_key"; then
        return
    fi

    echo ">> No API key configured for provider '$provider'."
    echo ">> Enter a key now (input hidden). Leave empty to switch to mock mode."
    local entered_key=""
    read -r -s -p "   ${provider^^} API key: " entered_key
    echo ""

    if [ -z "$entered_key" ]; then
        echo ">> No key entered. Switching to mock/local mode."
        export LLM_PROVIDER="mock"
        export LLM_MODEL="local"
        echo ">> This change is only for current run."
        return
    fi

    export "$key_var=$entered_key"
    read -r -p ">> Save key to .env for future runs? (y/N): " save_key
    if [[ "$save_key" =~ ^[Yy]$ ]]; then
        upsert_env_value "$key_var" "$entered_key"
        upsert_env_value "LLM_PROVIDER" "$provider"
        if [ -z "${LLM_MODEL:-}" ] || [ "${LLM_MODEL}" = "local" ] || [ "${LLM_MODEL}" = "qualcomm-internal" ]; then
            case "$provider" in
                qgenie) upsert_env_value "LLM_MODEL" "gpt-4o" ;;
                openai) upsert_env_value "LLM_MODEL" "gpt-4o" ;;
                anthropic) upsert_env_value "LLM_MODEL" "claude-3-5-sonnet-latest" ;;
                qualcomm) upsert_env_value "LLM_MODEL" "qualcomm-internal" ;;
            esac
        fi
    fi
}

check_qgenie_and_patchwise() {
    echo ""
    echo "🔵 Checking QGenie connectivity..."
    local qgenie_key=""
    if [ -f "$ENV_FILE" ]; then
        qgenie_key=$(grep -E '^QGENIE_API_KEY=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)
    fi
    qgenie_key="${qgenie_key%\"}"
    qgenie_key="${qgenie_key#\"}"
    qgenie_key="${qgenie_key%\'}"
    qgenie_key="${qgenie_key#\'}"

    if [ -z "$qgenie_key" ] || [ "$qgenie_key" = "your-qgenie-api-key-here" ]; then
        echo "  ⚠️  WARNING: QGENIE_API_KEY not set in .env"
        echo "  ⚠️  Agents will fall back to OPENAI_API_KEY/ANTHROPIC_API_KEY if set"
        echo "  💡  Get your QGenie key: https://qgenie-chat.qualcomm.com"
        echo ""
    else
        local qgenie_url
        qgenie_url=$(grep -E '^QGENIE_BASE_URL=' "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2-)
        qgenie_url="${qgenie_url:-https://qgenie-chat.qualcomm.com/v1}"
        echo "  ✅ QGenie API key detected"
        echo "  🌐 Provider: $qgenie_url"
    fi

    echo "🔧 Checking PatchWise installation..."
    local check_image="$IMAGE_NAME"
    if docker image inspect patchwise-backend >/dev/null 2>&1; then
        check_image="patchwise-backend"
    fi
    if docker image inspect "$check_image" >/dev/null 2>&1; then
        if docker run --rm "$check_image" patchwise --version > /dev/null 2>&1; then
            echo "  ✅ PatchWise installed and ready"
        else
            echo "  ⚠️  PatchWise not found in image yet — it will be available after build/install"
        fi
    else
        echo "  ℹ️  Docker image not built yet; PatchWise check will run after first build"
    fi
    echo ""
}

# ── Resolve port and update .env ─────────────────────────────
resolve_port() {
    local requested_port=${APP_PORT:-$DEFAULT_PORT}
    local actual_port=$(find_free_port $requested_port)

    if [ "$actual_port" != "$requested_port" ]; then
        echo ">> Port $requested_port busy — using port $actual_port"
        sed -i "s/^APP_PORT=.*/APP_PORT=$actual_port/" "$ENV_FILE"
        export APP_PORT=$actual_port
    else
        export APP_PORT=$actual_port
    fi
    echo $actual_port
}

# ── Commands ─────────────────────────────────────────────────

cmd_start() {
    print_banner
    setup_env
    prompt_for_missing_llm_key
    check_qgenie_and_patchwise

    echo ">> Checking Docker image..."
    if [[ "$(docker images -q $IMAGE_NAME 2>/dev/null)" == "" ]]; then
        echo ">> Image not found. Building now (this may take a few minutes)..."
        docker compose build
    fi

    local port=$(resolve_port)
    echo ">> Starting PatchWise on port $port..."
    docker compose up -d

    echo ""
    echo "  ┌────────────────────────────────────────────────────┐"
    echo "  │  ✅ PatchWise is starting up!                       │"
    echo "  │                                                      │"
    echo "  │  🌐 Open: http://localhost:$port                      │"
    echo "  │                                                      │"
    echo "  │  Note: First startup may take 30-40 seconds         │"
    echo "  │  Run './run.sh logs' to watch startup progress       │"
    echo "  └────────────────────────────────────────────────────┘"
    echo ""
}

cmd_stop() {
    echo ">> Stopping PatchWise..."
    docker compose down
    echo ">> PatchWise stopped."
}

cmd_restart() {
    echo ">> Restarting PatchWise..."
    docker compose restart
    echo ">> PatchWise restarted."
}

cmd_rebuild() {
    setup_env
    prompt_for_missing_llm_key
    check_qgenie_and_patchwise
    echo ">> Rebuilding PatchWise (applying .env changes)..."
    docker compose down
    docker compose build
    docker compose up -d --force-recreate
    echo ">> PatchWise rebuilt and started."
}

cmd_rebuild_clean() {
    setup_env
    prompt_for_missing_llm_key
    check_qgenie_and_patchwise
    echo ">> Rebuilding PatchWise with --no-cache..."
    docker compose down
    docker compose build --no-cache
    docker compose up -d --force-recreate
    echo ">> PatchWise clean rebuild completed."
}

cmd_logs() {
    echo ">> Streaming PatchWise logs (Ctrl+C to stop)..."
    docker compose logs -f
}

cmd_status() {
    echo ">> PatchWise container status:"
    docker compose ps
    echo ""
    source "$ENV_FILE" 2>/dev/null || true
    local port=${APP_PORT:-$DEFAULT_PORT}
    echo ">> Health check: http://localhost:$port/api/health"
    curl -s "http://localhost:$port/api/health" | python3 -m json.tool 2>/dev/null || echo "   (Container may still be starting up)"
}

cmd_clean() {
    echo "⚠️  WARNING: This will remove all containers AND volumes (data will be lost)!"
    read -p "   Are you sure? (yes/no): " confirm
    if [ "$confirm" == "yes" ]; then
        docker compose down -v --remove-orphans
        docker rmi $IMAGE_NAME 2>/dev/null || true
        echo ">> PatchWise fully cleaned."
    else
        echo ">> Cancelled."
    fi
}

cmd_seed() {
    echo ">> Seeding LKML knowledge base (ALSA/ASoC audio subsystem)..."
    echo ">> This may take 10-20 minutes depending on network speed."
    docker compose exec patchwise python3 /app/backend/scripts/lkml_preseeder.py
    echo ">> Seeding complete! Update .env: LKML_PRESEEDED=true"
}

cmd_shell() {
    echo ">> Opening shell inside PatchWise container..."
    docker compose exec patchwise /bin/bash
}

# ── Help ─────────────────────────────────────────────────────
cmd_help() {
    print_banner
    echo "  Usage: ./run.sh [command]"
    echo ""
    echo "  Commands:"
    echo "    start     Start PatchWise (auto-finds free port)"
    echo "    stop      Stop PatchWise"
    echo "    restart   Restart containers"
    echo "    rebuild   Rebuild using Docker cache (fast, default)"
    echo "    rebuild-clean Full rebuild with --no-cache (slow)"
    echo "    logs      Stream container logs"
    echo "    status    Show container status + health check"
    echo "    seed      Pre-seed LKML knowledge base (ALSA/ASoC)"
    echo "    shell     Open shell inside container"
    echo "    clean     Remove containers + volumes (⚠️ data loss!)"
    echo "    help      Show this help"
    echo ""
    echo "  Examples:"
    echo "    ./run.sh               # Start (default)"
    echo "    ./run.sh rebuild       # After .env changes"
    echo "    ./run.sh logs          # Debug startup issues"
    echo "    ./run.sh seed          # Pre-seed KB before first use"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────
COMMAND=${1:-start}

case $COMMAND in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    rebuild) cmd_rebuild ;;
    rebuild-clean) cmd_rebuild_clean ;;
    logs)    cmd_logs ;;
    status)  cmd_status ;;
    seed)    cmd_seed ;;
    shell)   cmd_shell ;;
    clean)   cmd_clean ;;
    help|--help|-h) cmd_help ;;
    *)
        echo "❌ Unknown command: $COMMAND"
        cmd_help
        exit 1
        ;;
esac
