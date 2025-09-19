# Shipped Log

Lightweight running log of changes, checkpoints, and next steps. Append new entries at the top with ISO timestamps so we can resume quickly if a session breaks.

---

## 2025-09-18T10:00:00Z

What we shipped today:
- Web UI: React (Vite) SPA with Extract/Settings tabs; Slack channel picker; Notion parent picker.
- Backend (FastAPI): Telegram/Slack/Notion endpoints; task tracking; static SPA serving under `/app`.
- Production build: Vite `base` set to `/app`; SPA loads correctly in prod.
- Telegram: login API endpoints + helper; session persisted; fixed `min_id` default; robust export via subprocess from API.
- Slack: graceful fallback if `groups:read` missing; verified end-to-end export; noted token `account_inactive` later.
- Autosave: Slack token and Telegram API ID/Hash/Phone + defaults persist to `config.json` automatically.
- One‑click launchers: `start_app.ps1/.cmd` to start and open browser; `stop_app.ps1/.cmd` to stop server.
- Windows tray app: `tray_app.ps1/.cmd` with Open/Start/Stop/Exit menu.
- Repo: initialized and pushed to `oregpt/slack_telegram_scraper` (branch `main`).

Fixes & polish:
- Fixed React blank page (hook ordering) and input focus loss while typing.
- Updated UI labels to mark Slack as supported; README updated.

Validated:
- Slack export to JSONL (channel `#extracttest`) — success after inviting bot.
- Telegram export to JSONL from `@cantyAI_bot` — success (5 messages sample).

Next up:
- Optional: add SSE/WebSocket log streaming to replace polling.
- Optional: Slack auto‑join public channels when `channels:join` is present.
- Optional: serve SPA also at `/` in addition to `/app`.

## 2025-09-19T07:54:11Z

Next TODO:
- Discord: run E2E export with provided bot token, target guild, and channel (JSONL, limit 100) and validate output.
- Optional: add Discord media download toggle in UI (already supported in exporter).
- Optional: add SSE/WebSocket task logs for real-time streaming.

