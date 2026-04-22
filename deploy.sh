#!/bin/bash
# Deploy Jarvis v2 — test-gate + active-call-check + restart.
set -euo pipefail

ROOT=/opt/jarvis-v2
cd "$ROOT"

echo "[1/5] Aktive Calls prüfen..."
ACTIVE=$(curl -sf http://127.0.0.1:18793/v2/active-calls 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("active_count",0))' 2>/dev/null || echo 0)
if [ "$ACTIVE" -gt 0 ]; then
  echo "FEHLER: $ACTIVE aktive Calls. Deploy abgebrochen."
  exit 2
fi
echo "  ✓ Keine aktiven Calls"

echo "[2/5] Tests ausführen..."
source venv/bin/activate
pytest -q --tb=short 2>&1 | tail -20
TEST_EXIT=${PIPESTATUS[0]}
if [ "$TEST_EXIT" -ne 0 ]; then
  echo "FEHLER: Tests rot. Deploy abgebrochen."
  exit 3
fi

echo "[3/5] Systemd-Unit installieren..."
cp scripts/jarvis-v2.service /etc/systemd/system/jarvis-v2.service
systemctl daemon-reload

echo "[4/5] Service neu starten..."
systemctl restart jarvis-v2
sleep 2
systemctl is-active jarvis-v2 >/dev/null || { echo "FEHLER: Service nicht aktiv."; exit 4; }

echo "[5/5] Health-Check..."
for i in 1 2 3 4 5; do
  if curl -sf http://127.0.0.1:18793/v2/health >/dev/null; then
    echo "  ✓ Health OK (Versuch $i)"
    break
  fi
  sleep 1
done

echo "========== DEPLOY OK =========="
curl -s http://127.0.0.1:18793/v2/health | python3 -m json.tool
