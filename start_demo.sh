#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# AI-Native Self-Healing DevOps Platform — Demo Launcher
# ─────────────────────────────────────────────────────────────
set -e

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║   AI-Native Self-Healing DevOps Platform             ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Env check ────────────────────────────────────────────────
if [ -f ".env" ]; then
  source .env
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo -e "${RED}ERROR: ANTHROPIC_API_KEY is not set.${NC}"
  echo "Copy .env.example to .env and fill in your key:"
  echo "  cp .env.example .env"
  exit 1
fi
echo -e "${GREEN}✓ ANTHROPIC_API_KEY is set${NC}"

# ── Install deps ─────────────────────────────────────────────
echo -e "\n${YELLOW}Installing dependencies…${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✓ Dependencies ready${NC}"

# ── Kill any leftover processes on our ports ──────────────────
for port in 5000 5001 5002; do
  pid=$(lsof -ti tcp:$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo -e "${YELLOW}Killing existing process on port $port (PID $pid)${NC}"
    kill -9 $pid 2>/dev/null || true
  fi
done
sleep 0.5

# ── Start services ────────────────────────────────────────────
echo -e "\n${BOLD}Starting services…${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python "$SCRIPT_DIR/webhook_receiver.py" &
PID_WEBHOOK=$!
echo -e "${GREEN}✓ Webhook Receiver  →  http://localhost:5000  (PID $PID_WEBHOOK)${NC}"
sleep 0.5

python "$SCRIPT_DIR/ai_agent.py" &
PID_AI=$!
echo -e "${GREEN}✓ AI Agent          →  http://localhost:5001  (PID $PID_AI)${NC}"
sleep 0.5

python "$SCRIPT_DIR/integrations.py" &
PID_INT=$!
echo -e "${GREEN}✓ Integrations      →  http://localhost:5002  (PID $PID_INT)${NC}"
sleep 1

# ── Health checks ────────────────────────────────────────────
echo -e "\n${YELLOW}Checking service health…${NC}"
all_ok=true
for url in "http://localhost:5000/health" "http://localhost:5001/health" "http://localhost:5002/health"; do
  if curl -sf "$url" > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ $url${NC}"
  else
    echo -e "${RED}  ✗ $url — not responding${NC}"
    all_ok=false
  fi
done

if [ "$all_ok" = false ]; then
  echo -e "\n${RED}Some services are not healthy. Check logs above.${NC}"
fi

# ── Ready ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   ALL SERVICES RUNNING — DEMO READY                 ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}1.${NC} Open the dashboard:  ${CYAN}http://localhost:5000/${NC}"
echo -e "  ${BOLD}2.${NC} Trigger a failure:   ${CYAN}python demo_trigger.py${NC}"
echo -e "  ${BOLD}3.${NC} List all scenarios:  ${CYAN}python demo_trigger.py list${NC}"
echo -e "  ${BOLD}4.${NC} Run all scenarios:   ${CYAN}python demo_trigger.py all${NC}"
echo ""
echo -e "Press ${BOLD}Ctrl+C${NC} to stop all services."
echo ""

# ── Trap Ctrl+C ───────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Shutting down…${NC}"
  kill $PID_WEBHOOK $PID_AI $PID_INT 2>/dev/null || true
  echo -e "${GREEN}Done.${NC}"
  exit 0
}
trap cleanup INT TERM

# Wait for any child to exit
wait
