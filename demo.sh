#!/usr/bin/env bash
# Run NessWell locally with sample data. No accounts, nothing deployed.
#
#   ./demo.sh            start (seeds sample data the first time)
#   ./demo.sh --reset    fresh sample data
#   ./demo.sh --empty    wipe it and log from scratch
#
# Needs: Docker (for the database), Python 3.12+, Node 18+.
# Already running Postgres? Set DATABASE_URL to it and Docker is skipped.
set -euo pipefail
cd "$(dirname "$0")"
SEED_ARGS="${1:-}"

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2"; exit 1; }; }

need python3 "Install Python 3.12+ from python.org."
need npm "Install Node.js 18+ from nodejs.org."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || { echo "Python 3.12+ is needed (you have $(python3 --version))."; exit 1; }

# ---------- database ----------
if [ -z "${DATABASE_URL:-}" ]; then
  need docker "Install Docker Desktop, or set DATABASE_URL to a local Postgres."
  say "Starting the database (Docker)…"
  docker compose up -d db
  export DATABASE_URL="postgresql+psycopg://nesswell:nesswell@localhost:5433/nesswell"
  for _ in $(seq 1 30); do
    docker compose exec -T db pg_isready -U nesswell >/dev/null 2>&1 && break
    sleep 1
  done
fi

# ---------- API ----------
say "Setting up the API…"
cd backend
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

export DEV_MODE=true
export CRON_SECRET="${CRON_SECRET:-local-demo}"
# Keys for push + Garmin, generated once and kept in backend/.demo-keys
if [ ! -f .demo-keys ]; then
  { python3 scripts/gen_vapid.py; python3 scripts/gen_garmin_key.py; } > .demo-keys
fi
set -a; source .demo-keys; set +a

alembic upgrade head
python3 scripts/seed_demo.py $SEED_ARGS

say "Starting the API on port 8000…"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
cd ..

# ---------- app ----------
say "Starting the app…"
cd frontend
[ -d node_modules ] || npm install --silent
LAN_IP="$( (ipconfig getifaddr en0 || hostname -I 2>/dev/null | awk '{print $1}') 2>/dev/null || true)"
say "NessWell demo is running:
  On this computer:  http://localhost:5173
  On your phone:     http://${LAN_IP:-your-computer-ip}:5173  (same wifi)
Press Ctrl+C to stop."
npm run demo -- --port 5173 --strictPort
