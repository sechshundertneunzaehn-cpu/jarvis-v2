# Jarvis v2 — Architektur-Entscheidungen

Stand: 2026-04-22 (Initial Build-Sprint).

## Laufzeit-Umgebung

- Host: Helsinki 89.167.38.29 (Ubuntu 24.04, Python 3.12)
- Verzeichnis: `/opt/jarvis-v2`
- Port: `127.0.0.1:18793` (intern, per nginx exposiert unter `https://translate.dream-code.app/v2/`)
- Service: `systemd` unit `jarvis-v2.service`, standard **disabled** bis alle Gates grün
- Logs: `/var/log/jarvis-v2/app.log` (JSON) + `stdout.log` / `stderr.log`

## Stack (fix, nicht verhandelbar)

| Komponente | Wahl |
|------------|------|
| ASGI | FastAPI + uvicorn |
| Telefonie | Twilio Programmable Voice, Conference-basiert |
| STT | Deepgram Nova-3, multi-lang, µ-law 8 kHz, VAD + utterance_end |
| Brain | Anthropic `claude-sonnet-4-7` (fallback `claude-sonnet-4-6`), Streaming + Tools |
| TTS | Deepgram Aura-2 (fabian-de / orion-en / cevheri-tr) |
| Contacts | YAML, RapidFuzz WRatio (≥80) |
| Knowledge | Markdown + paragraph-granular RapidFuzz partial/token-set |

## Call-Architektur

1. Inbound ruft `POST /v2/twilio/voice-inbound`.
2. Server öffnet neue `Session` (pair_id, conference_name=`pair-<id>`).
3. User-Leg bekommt TwiML `<Dial><Conference>` → startet die Conference.
4. Parallel wird ein **Bot-Leg** via Twilio REST `calls.create` gestartet. Die
   Answer-URL ist `/v2/twilio/voice-bot-join?pair_id=<id>` und antwortet mit
   `<Connect><Stream>` auf den WS `/v2/twilio/stream/<pair>/bot`. So bekommen
   wir die Bot-Audio bidirektional, während Twilio das Mixing macht.
5. Outbound-Dial (Tool `dial_contact`) ruft intern `POST /v2/twilio/outbound-dial`,
   das einen dritten Leg aufbaut, dessen Answer-URL `<Dial><Conference>` auf
   dieselbe pair-UUID ist.

Drei Legs + eine Conference – der Server forwarded keine Audio zwischen Legs.

## Phase-Machine

`INIT → RINGING → GREETING → AUTHED → {INTERPRETER|ASSISTANT} → DIALING → BRIDGED → ENDED`

## Modi

- **assistant**: Jarvis-Persona, alle 8 Tools verfügbar
- **interpreter**: reiner Live-Dolmetscher, nur Control-Tools (`hangup`, `set_mode`)

## Owner-Auth

- Whitelist: Caller-ID-Match (config.yaml → `auth.owner_whitelist`)
- Fallback: Passphrase "Sonne über Wyoming" mit RapidFuzz Toleranz ≥75
- Non-Owner: bleibt im Basic-Interpreter, keine Tool-Calls erlaubt

## Cost Control

- Meter pro Call: Twilio voice + conf, Deepgram STT + TTS, Claude input + output
- Default-Cap: $5 pro Call (config.yaml, per-call override möglich)
- Warn bei 75 % → Agent sagt "noch 25 % Budget", Hangup bei 100 % → `soft_hangup`

## Edge-Case-Entscheidungen

- **Model-IDs** (live-verifiziert 2026-04-22): Primary ist `claude-sonnet-4-6`, Fallback `claude-sonnet-4-5-20250929`. Der Spec-Wunsch `claude-sonnet-4-7` gab in der ersten Live-Anfrage HTTP 404 (nicht verfügbar); der Fallback-Pfad griff automatisch. Wenn 4-7 verfügbar wird, reicht ein Config-Swap — kein Code-Change.
- **Bot-Leg-Schutz**: `/voice-inbound` spawnt den Bot-Leg nur wenn `X-Twilio-Signature`-Header anliegt. So kann man per `curl` smoke-testen ohne echte Twilio-Calls auszulösen.
- STT liefert `is_final && speech_final` → wir lösen einen Agent-Turn aus. `interim` wird nur geloggt. `utterance_end` ist Fallback wenn `speech_final` ausbleibt.
- History: 30 Turns; bei Überlauf wird das Älteste abgeschnitten. Tool-Result-Blocks zählen nicht als Turn.
- Aura-2 TR (`cevheri-tr`) laut Deepgram v4-Roadmap verfügbar; falls 400er → Fallback auf `aura-asteria-en`.
- Conference `end_conference_on_exit` ist am **User-Leg** gesetzt: User legt auf ⇒ Call endet. Bot-Leg darf nicht den Conference-End triggern.

## Nicht-Ziele (bewusst raus)

- Email / Kalender / Browser-Automation
- Multi-Call-Routing (Askin callt Askin während Jarvis aktiv ist)
- Aufnahmen / Recording (DSGVO-Aufwand lohnt sich jetzt nicht)

## Rollback

`scripts/rollback.sh` → stoppt + disabled Service. Twilio-Webhook muss manuell
zurück auf `/voice` (kitranslator-api) oder `/v1/twilio/voice-inbound` (jarvis-v1) gesetzt werden.
