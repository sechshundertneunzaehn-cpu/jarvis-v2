# Jarvis v2 — Runbook

## Deploy

```bash
ssh -i ~/.ssh/id_rsa_ai-server root@89.167.38.29
cd /opt/jarvis-v2
./deploy.sh
```

Deploy-Gate: aktive-Call-Check + Test-Suite + systemd restart + Health.

## Stop / Disable (Rollback)

```bash
bash /opt/jarvis-v2/scripts/rollback.sh
# Twilio Console: Voice-Webhook für +13076670667 auf
#   https://translate.dream-code.app/voice     (kitranslator-api)
# oder
#   https://translate.dream-code.app/v1/twilio/voice-inbound  (jarvis-v1)
# zurücksetzen.
```

## Health + Live-Monitoring

```bash
curl -sf http://127.0.0.1:18793/v2/health | jq
curl -sf http://127.0.0.1:18793/v2/active-calls | jq
journalctl -u jarvis-v2 -f
tail -f /var/log/jarvis-v2/app.log
```

## Test

```bash
cd /opt/jarvis-v2
source venv/bin/activate
pytest -q
```

## Smoke-Test

```bash
./scripts/smoke_test.sh
# Dann manuell von +18042221111 gegen die Twilio-Nummer anrufen
# und in einem anderen Terminal journalctl -u jarvis-v2 -f beobachten.
```

## Debug: häufige Störungen

| Symptom | Vermutung | Aktion |
|---------|-----------|--------|
| 502 bei `/v2/twilio/stream/...` | nginx Upgrade-Header fehlt | `scripts/nginx-v2.conf` prüfen |
| Stream verbindet, kein Audio | Deepgram-Key leer | `grep DEEPGRAM /opt/jarvis-v2/.env` |
| "insufficient_quota" in Logs | Anthropic-Credit leer | Key in `.env` rotieren |
| Conference startet nicht | `beep=false` nicht gesetzt oder zweiter Leg kam nicht rein | `conference-events` Log prüfen |
| Bot antwortet nicht | Tool-Dispatch crash | `journalctl -u jarvis-v2 --since '5 min ago' \| grep ERROR` |

## Incident: Cost-Cap gerissen

1. Auto-Hangup sollte greifen. Falls nicht:
   `curl -X POST "$BASE/v2/admin/kill/<pair_id>"` (TODO v2.1)
   oder in Twilio Console: "End call" auf allen Legs.
2. Breakdown in den Logs nach `"event":"cost_breakdown"` suchen.
3. Cap in `config.yaml` senken bis Ursache geklärt.

## Secrets

- `/opt/jarvis-v2/.env` — `chmod 600 root:root`
- NIE in Git, NIE in Logs, NIE in Telegram.
- Rotation: Key tauschen → `systemctl restart jarvis-v2`.
