# Jarvis v2 - Error Log & Lessons Learned

ZWECK: Jeder Fix hier dokumentiert. Vor neuem Fix: Error_Log lesen. Keine Wiederholungen.
Format pro Eintrag: Symptom / Root Cause / Lesson / Fix-Commit.

---

## E-001: thalia-de Voice existiert nicht (2026-04-22)
Symptom: Anruf, Deepgram HTTP 400, kein Audio.
Root Cause: Web-Claude empfahl Voice aus dem Kopf, ohne GET /v1/models vorher.
Lesson: Alle TTS-Voice-IDs per API verifizieren, nie raten.
Fix-Commit: aurelia/julius ersetzt.

## E-002: speed= URL-Param unsupported (2026-04-22)
Symptom: Deepgram 400.
Root Cause: Aura-2 lehnt speed= im URL ab.
Lesson: Erst curl-Test ob Param 200 liefert, DANN in Code.
Fix-Commit: Open: speed als Body-Param oder SSML-Text noch ungetestet.

## E-003: Sandbox-Egress blockt bridge.dream-code.app (2026-04-22)
Symptom: Web-Claude kann Bridge nicht pollen trotz Token.
Root Cause: host_not_allowed auf Egress-Level.
Lesson: Vor neuen Sync-Kanalen erst web_fetch-Test machen.
Fix-Commit: Google Drive Bridge stattdessen.

## E-004: Drive Multi-Account-Clash (2026-04-22)
Symptom: Create-file in Bridge-Ordner gab Internal Error.
Root Cause: Claude-Connector unter anderem Google-Account als rclone. drive.file-Scope unsichtbar fuer anderes Account.
Lesson: Bei MCP-Connector immer Account verifizieren (testdatei anlegen, in Browser pruefen).
Fix-Commit: Connector reconnected.

## E-005: Mixer-Interleaving FIFO-hub (2026-04-23)
Symptom: Jarvis klingt 2x langsam und abgehackt.
Root Cause: TTS-Frames + Target-Audio-Frames gehen in dieselbe user-Queue (FIFO, kein Sample-Sum). Interleaving = halbe Sprechrate.
Lesson: AudioHub ist kein echter Mixer; zwei Producer parallel vermischen sich timesliced.
Fix-Commit: 39ab8c6 - target->user bei tts_active=True stumm.

## E-006: Clipping durch boost 1.25x (2026-04-23)
Symptom: jarvis under verzerrt.
Root Cause: audioop.mul trunciert statt saturiert, clippt bei normaler TTS-Peak.
Lesson: Kein Boost > 1.0x mit audioop.mul ohne Limiter.
Fix-Commit: 39ab8c6 - boosted = frame.

## E-007: Autonomes Auflegen nach mode-Schaltung (2026-04-23)
Symptom: Jarvis legt auf, wenn User keine Antwort gibt oder in interpreter nichts kommt.
Root Cause: Claude-Agent ruft hangup-Tool autonom auf (kein Guard, Prompt erlaubte es implizit).
Lesson: USER COMMITED 2026-04-23 - JARVIS DARF NIE AUTONOM AUFLEGEN. NUR EXPLIZITER USER-BEFEHL.
Fix-Commit: F1D - (a) System-Prompt verbietet autonomes Auflegen hart, (b) brain/tools.py _hangup() prueft letzte User-Text-Turns auf Hangup-Phrasen und blockiert sonst mit hangup_trigger reason=blocked_no_explicit_user_command, (c) hangup-Schema-Description erweitert.

<-- Neue Eintraege unten anfuegen -->
