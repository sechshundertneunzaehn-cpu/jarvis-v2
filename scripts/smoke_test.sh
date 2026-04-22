#!/bin/bash
# Live smoke test — calls the Jarvis v2 number from a designated test number.
# Usage: TWILIO_TEST_FROM=+18042221111 ./scripts/smoke_test.sh
set -e
PORT=${PORT:-18793}
BASE="http://127.0.0.1:$PORT"

echo "== Health =="
curl -sf "$BASE/v2/health" | python3 -m json.tool

echo "== Ping =="
curl -sf "$BASE/v2/ping" && echo

echo "== Active calls =="
curl -sf "$BASE/v2/active-calls" | python3 -m json.tool

echo "== Inbound TwiML shape =="
curl -sf -X POST "$BASE/v2/twilio/voice-inbound" \
  -d "From=+13076670667&To=+18772395494&CallSid=CA_smoke_$$" | head -c 400
echo

echo ""
echo "Live call test requires manually placing a call to the Twilio number"
echo "and observing /v2/active-calls and journalctl -u jarvis-v2 -f."
