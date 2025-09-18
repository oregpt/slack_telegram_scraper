# ChatTools Exporter v0.1.0 — Release Notes (Draft)

Highlights
- React Web UI (Vite) served by FastAPI or via dev server.
- FastAPI backend with task tracking, CORS, and static SPA.
- Telegram export (Telethon): filters, resume, media (FS), Notion sink.
- Slack export: filters, optional media download, Notion sink.
- Pickers: Slack channel search; Notion page/database search.

CLI/Server
- `chattools-exporter-server` entry point to run the API.
- PowerShell helpers: `run_server.ps1`, `run_web.ps1`, `run_web_build.ps1`.

Breaking Changes
- None (new project layout for web/API in addition to Tk UI and CLI).

Known Issues / Caveats
- Telegram: Login endpoints run via a helper to avoid event loop issues; session is persisted at `src/chattools_exporter/tg_export.session`.
- Telegram: Subprocess is used for file exports from API for robustness.
- Slack: For private channels, the bot must be a member; for public-only scope, channel search falls back gracefully.
- Web: Production SPA is served under `/app` path.

Upgrade Notes
- Install Python deps (first run does this automatically in scripts): `pip install -r requirements.txt`.
- For web dev: Node 18+, run `npm install` then `npm run dev` in `web/`.

Verification Steps
1) Start API: `./run_server.ps1` (http://localhost:8000/api/health).
2) Dev web: `./run_web.ps1` (http://localhost:5173) or build: `./run_web_build.ps1` and browse http://localhost:8000/app.
3) Slack: Test token in Settings, pick channel, export to JSONL.
4) Telegram: Test login (code + optional 2FA), export to JSONL (or Notion).

