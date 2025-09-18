# ChatTools Exporter

Export chat history with a simple UI. Supports Telegram (via Telethon) with optional Notion export, and Slack (via slack_sdk). Teams is surfaced in the UI as a future target.

Shipped Log: See `shippedlog.md` for a timestamped running log of shipped changes and next steps.

Features:
- Telegram export (user session) with filters: date range, only media/text, keywords, specific users, limit.
- Output: JSONL/CSV to local folder OR directly to Notion (Database or Page).
- Resume (JSONL), reverse order, optional media download (local output).
- Minimal 2-tab UI: Extract and Settings. Settings persist in `config.json`; Telethon session persists in `.session`.
- Notion: save multiple destinations by name; Pick Parent helper and two write modes (per message, group by day).

## New: Web UI (React)
You can now run a local web server and open a browser UI that mirrors the existing desktop features.

### Start the backend API (FastAPI)

```powershell
cd "C:\Users\oreph\Documents\SCRAPPING TOOLS\chattools-exporter"
./run_server.ps1 -Port 8000
```

This creates a virtualenv on first run and serves the API at `http://localhost:8000`.

### Start the React frontend (Vite)

Requirements: Node 18+ and npm.

```powershell
cd "C:\Users\oreph\Documents\SCRAPPING TOOLS\chattools-exporter\web"
npm install
npm run dev
```

Open the URL shown by Vite (default `http://localhost:5173`). The frontend calls the local API.

### Production build (served by FastAPI)

```powershell
cd "C:\Users\oreph\Documents\SCRAPPING TOOLS\chattools-exporter"
./run_web_build.ps1   # builds to web/dist
./run_server.ps1      # serves API + static web at http://localhost:8000/app
```

Notes:
- Slack channel picker: use the Extract tab, choose Slack, click "Pick Channel…" and search; choose by `#name` or by ID.
- Notion parent picker: in Settings → Notion Destinations, enter your API key then "Pick Parent…" to search pages/databases and set Type + Parent ID.

### One‑click launcher

- Start everything and open browser:
  - Double‑click `start_app.cmd` (or run `./start_app.ps1 -Port 8000`)
- Stop the background server:
  - Double‑click `stop_app.cmd` (or run `./stop_app.ps1`)

## Prerequisites
- Python 3.9+ installed (`py -3 --version` on Windows)
- Telegram API credentials (`api_id`, `api_hash`): https://my.telegram.org
- You must be a member of private groups or the group/channel must be public.
- For Notion export: a Notion integration (secret) shared to your target Page/Database.

## Quick Start (Windows)
1) Open PowerShell in this folder: `Documents/SCRAPPING TOOLS/chattools-exporter`
2) First run creates a virtualenv and installs dependencies automatically.

### Option A: Simple UI

```powershell
./run_ui.ps1
```

Then:
- Settings tab: enter API ID, API Hash, phone; click Test Login.
- Notion destinations: add your Notion Integration key and a Parent (Database or Page) under Notion Destinations, then Save and Test Connection.
- Use "Pick Parent..." to search and choose a database or page interactively.
- Extract tab: fill chat, filters. Choose Destination:
  - Folder (local): choose output folder and filename.
  - Notion: pick one of your saved destinations (folder/filename ignored). Choose Notion write mode:
    - `per_message`: one Notion page (or DB row) per message.
    - `group_by_day`: one child page per day under the selected Page parent; messages become blocks inside.
  Click Extract.

### Option B: CLI Examples

```powershell
# JSONL export (recommended for large datasets)
./run_export.ps1 --api-id 123456 --api-hash abcdef1234567890 \
  --chat @public_group --out export.jsonl --reverse --resume

# CSV export
./run_export.ps1 --api-id 123456 --api-hash abcdef1234567890 \
  --chat "https://t.me/some_public_channel" --out export.csv --format csv --reverse

# With media download
./run_export.ps1 --api-id 123456 --api-hash abcdef1234567890 \
  --chat -1001234567890 --out export.jsonl --reverse --media-dir media

# Slack export (token via --token or env SLACK_TOKEN)
./run_export_slack.ps1 --token xoxb-... --channel "#general" --out slack.jsonl --reverse --limit 200
```

On first run you will be prompted to enter your phone number and login code (and 2FA if enabled). A `.session` file will be created to reuse your login.
 
### Option C: Install as a package (optional)

```powershell
py -3 -m pip install --upgrade pip
py -3 -m pip install -e .

# Now you can run the scripts globally in your environment:
chattools-exporter-ui
chattools-exporter --api-id 123456 --api-hash abcdef... --chat @public_group --out export.jsonl --reverse --resume
chattools-exporter-server
```

## Arguments
- `--api-id` / `--api-hash`: Your Telegram API credentials. You can also set env vars `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- `--session`: Session filename (default `tg_export.session`).
- `--chat`: Target chat (`@username`, `https://t.me/...`, or numeric id like `-100123...`).
- `--out`: Output file path. Infers format by extension or set `--format`.
- `--format`: `jsonl` or `csv`.
- `--reverse`: Export oldest to newest (good for resume and stable ordering).
- `--resume`: Resume based on last `id` in an existing JSONL file.
- `--limit`: Limit number of messages.
- `--media-dir`: Directory to download media files.
- `--min-date` / `--max-date`: Filter by date (YYYY-MM-DD).
- `--only-media` / `--only-text`: Filter messages by presence of media.

## Tips
- JSONL is safer for very large exports and supports append + resume cleanly.
- If media downloading hits rate limits, the tool will sleep and retry.
- You can re-run with `--resume` to continue after an interruption.

## Environment Variables (optional)
Instead of passing credentials on every run, you can set them in your session:

```powershell
$env:TELEGRAM_API_ID = "123456"
$env:TELEGRAM_API_HASH = "abcdef1234567890"
```

Then you can omit `--api-id` and `--api-hash` in the command.

## Notes
- Bots cannot backfill history; use a user account.
- You must have access to the group/channel’s history to export it.

## Notion Setup
- Create an integration at https://www.notion.so/my-integrations and copy the secret.
- Share your Database/Page with the integration (Share → Invite…).
- Use “Pick Parent…” to search and select your target. Or paste a Database/Page ID.
- Modes:
  - `per_message`: one DB row or child page per message.
  - `group_by_day`: one child page per day (Page parent only) with messages as blocks.

## Slack Setup
- Create a Slack app or use an existing token (bot or user). Scopes typically needed: `channels:history`, `groups:history`, `channels:read`, `groups:read`, and for media downloads `files:read`.
- Put the token in Settings → Slack and click “Test Slack”, or pass `--token` / set env var `SLACK_TOKEN`.
- Channel may be `#name` or a channel ID (e.g., `C0123456789`). Private channels require the token to be a member.

## Project Structure
```
Documents/SCRAPPING TOOLS/chattools-exporter/
  src/
    chattools_exporter/
      __init__.py
      export_telegram.py   # Exporter library + CLI module
      ui_app.py            # Tkinter UI (Extract + Settings)
      notion_writer.py     # Notion client + sinks
  run_ui.ps1               # Launches UI (creates venv, installs deps)
  run_export.ps1           # Runs CLI exporter
  requirements.txt         # Python deps
  .gitignore               # Ignores venv, session, outputs
  README.md                # This file
```

## Pushing To GitHub (manual)
If you want this folder to be the root of `chattools-exporter`:

1) Open PowerShell here:
```
cd "C:\Users\oreph\Documents\SCRAPPING TOOLS\chattools-exporter"
```
2) Initialize and push (if the repo already exists at GitHub and is empty):
```
git init
git add .
git commit -m "Initial commit: Telegram exporter UI + Notion"
git branch -M main
git remote add origin https://github.com/oregpt/chattools-exporter.git
git push -u origin main
```

If the repo does not exist yet, create it first in GitHub, or use GitHub CLI:
```
gh repo create oregpt/chattools-exporter --public -y --source . --remote origin --push
```

You may need to set your Git identity once:
```
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```
