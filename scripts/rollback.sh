#!/bin/bash
# Stop jarvis-v2 so the existing kitranslator-api webhook handles calls.
set -e
systemctl stop jarvis-v2 2>/dev/null || true
systemctl disable jarvis-v2 2>/dev/null || true
echo "jarvis-v2 gestoppt. Twilio-Webhook sollte auf /v1 oder kitranslator-api (/voice) zeigen."
echo "Prüfen:  curl -sf http://127.0.0.1:18791/health || echo legacy-down"
