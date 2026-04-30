#!/bin/bash

set -e

# ─────────────────────────────────────────────
#  PatchWise — Lifecycle Manager
#  Usage:
#    ./run.sh            → Start (default)
#    ./run.sh start      → Start containers
#    ./run.sh stop       → Stop containers
#    ./run.sh restart    → Restart containers
#    ./run.sh rebuild    → Force rebuild + restart
#    ./run.sh logs       → Tail all logs
#    ./run.sh status     → Show running containers
#    ./run.sh clean      → Remove containers + volumes
# ─────────────────────────────────────────────

BACKEND_DEFAULT_PORT=8000
FRONTEND_DEFAULT_PORT=3000
ENV_FILE=".env"
COMPOSE_FILE="docker-compose.yml"
APP_NAME="PatchWise"

# Colors
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

print_banner() {
  echo -e "${CYAN}"
  echo "  ██████╗  █████╗ ████████╗ ██████╗██╗  ██╗██╗    ██╗██╗███████╗███████╗"
  echo "  ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝██║  ██║██║    ██║██║██╔════╝██╔════╝"
  echo "  ██████╔╝███████║   ██║   ██║     ███████║██║ █╗ ██║██║███████╗█████╗  "
  echo "  ██╔═══╝ ██╔══██║   ██║   ██║     ██╔══██║██║███╗██║██║╚════██║██╔══╝  "
  echo "  ██║     ██║  ██║   ██║   ╚██████╗██║  ██║╚███╔███╔╝██║███████║███████╗"
  echo "  ╚═╝     ╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝╚══════╝╚══════╝"
  echo -e "${RESET}"
  echo -e "  ${BOLD}CHANAKYA (Reviewer) ⟷ ARYABHATA (Developer)${RESET}"
  echo ""
}

# ─── Find free port ───────────────────────────────────────────────────────────
find_free_port() {
  local port=$1
  while lsof -i:"$port" &>/dev/null 2>&1; do
    echo -e "  ${YELLOW}⚠  Port $port is in use — trying $((port + 1))...${RESET}"
    port=$((port + 1))
  done
  echo "$port"
}

# ─── Write .env file ──────────────────────────────────────────────────────────
setup_env() {
  BACKEND_PORT=$(find_free_port $BACKEND_DEFAULT_PORT)
  FRONTEND_PORT=$(find_free_port $FRONTEND_DEFAULT_PORT)

  if [ ! -f "$ENV_FILE" ]; then
    echo -e "  ${YELLOW}⚠  .env not found — creating from .env.example...${RESET}"
    if [ -f ".env.example" ]; then
      cp .env.example "$ENV_FILE"
    else
      touch "$ENV_FILE"
    fi
  fi

  # Update ports in .env
  if grep -q "BACKEND_PORT" "$ENV_FILE"; then
    sed -i "s/BACKEND_PORT=.*/BACKEND_PORT=$BACKEND_PORT/" "$ENV_FILE"
  else
    echo "BACKEND_PORT=$BACKEND_PORT" >> "$ENV_FILE"
  fi

  if grep -q "FRONTEND_PORT" "$ENV_FILE"; then
    sed -i "s/FRONTEND_PORT=.*/FRONTEND_PORT=$FRONTEND_PORT/" "$ENV_FILE"
  else
    echo "FRONTEND_PORT=$FRONTEND_PORT" >> "$ENV_FILE"
  fi

  echo -e "  ${GREEN}✔  Backend  → http://localhost:$BACKEND_PORT${RESET}"
  echo -e "  ${GREEN}✔  Frontend → http://localhost:$FRONTEND_PORT${RESET}"
  echo ""
}

# ─── Commands ─────────────────────────────────────────────────────────────────
cmd_start() {
  print_banner
  echo -e "  ${BOLD}▶  Starting $APP_NAME...${RESET}"
  echo ""
  setup_env
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
  echo ""
  echo -e "  ${GREEN}✅ $APP_NAME is running!${RESET}"
  echo ""
}

cmd_stop() {
  echo -e "  ${RED}■  Stopping $APP_NAME...${RESET}"
  docker compose -f "$COMPOSE_FILE" down
  echo -e "  ${GREEN}✔  Stopped.${RESET}"
}

cmd_restart() {
  echo -e "  ${YELLOW}↺  Restarting $APP_NAME...${RESET}"
  docker compose -f "$COMPOSE_FILE" down
  setup_env
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
  echo -e "  ${GREEN}✔  Restarted.${RESET}"
}

cmd_rebuild() {
  print_banner
  echo -e "  ${YELLOW}🔨 Rebuilding $APP_NAME (force)...${RESET}"
  setup_env
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build --force-recreate
  echo -e "  ${GREEN}✅ Rebuild complete!${RESET}"
}

cmd_logs() {
  docker compose -f "$COMPOSE_FILE" logs -f --tail=100
}

cmd_status() {
  docker compose -f "$COMPOSE_FILE" ps
}

cmd_clean() {
  echo -e "  ${RED}🗑  Cleaning $APP_NAME containers and volumes...${RESET}"
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans
  echo -e "  ${GREEN}✔  Clean complete.${RESET}"
}

# ─── Entry Point ──────────────────────────────────────────────────────────────
COMMAND=${1:-start}

case "$COMMAND" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  rebuild) cmd_rebuild ;;
  logs)    cmd_logs ;;
  status)  cmd_status ;;
  clean)   cmd_clean ;;
  *)
    echo -e "  ${RED}Unknown command: $COMMAND${RESET}"
    echo "  Usage: ./run.sh [start|stop|restart|rebuild|logs|status|clean]"
    exit 1
    ;;
esac
