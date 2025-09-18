import os
import json
import threading
import time
import uuid
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sys
import subprocess
import asyncio
import threading

from .export_telegram import export_messages as tg_export
from .export_slack import export_slack_messages as slack_export, test_slack_token
from .export_discord import export_discord_messages as discord_export
from .notion_writer import notion_sink, test_connection as notion_test

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except Exception:
    TelegramClient = None
    SessionPasswordNeededError = Exception


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DEFAULT_SESSION = os.path.join(APP_DIR, "tg_export.session")


def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "app": "Telegram",
        "telegram": {
            "api_id": "",
            "api_hash": "",
            "phone": "",
            "session": DEFAULT_SESSION,
        },
        "slack": {"token": ""},
        "notion": {"destinations": []},
        "defaults": {
            "reverse": True,
            "resume": True,
            "format": "jsonl",
            "only": "all",
            "last_output_folder": APP_DIR,
            "filename": "messages.jsonl",
            "destination": "Folder (local)",
            "notion_mode": "per_message",
        },
    }


def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class TelegramLoginStart(BaseModel):
    api_id: int
    api_hash: str
    phone: str
    session: Optional[str] = None


class TelegramLoginComplete(BaseModel):
    api_id: int
    api_hash: str
    phone: str
    code: str
    password: Optional[str] = None
    session: Optional[str] = None


class TelegramExtractRequest(BaseModel):
    api_id: int
    api_hash: str
    session: Optional[str] = None
    chat: str
    out: Optional[str] = None
    format: Optional[str] = None
    reverse: bool = True
    resume: bool = True
    limit: Optional[int] = None
    media_dir: Optional[str] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    only_media: bool = False
    only_text: bool = False
    keywords: Optional[list[str]] = None
    users: Optional[list[str]] = None
    # Notion destination (if provided, overrides local FS)
    notion_api_key: Optional[str] = None
    notion_dest_type: Optional[str] = Field(default=None, description="Database or Page")
    notion_parent_id: Optional[str] = None
    notion_mode: Optional[str] = Field(default="per_message")


class SlackExtractRequest(BaseModel):
    token: str
    channel: str
    out: Optional[str] = None
    format: Optional[str] = None
    reverse: bool = True
    resume: bool = True
    limit: Optional[int] = None
    media_dir: Optional[str] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    only_media: bool = False
    only_text: bool = False
    keywords: Optional[list[str]] = None
    users: Optional[list[str]] = None
    # Notion destination (if provided)
    notion_api_key: Optional[str] = None
    notion_dest_type: Optional[str] = None
    notion_parent_id: Optional[str] = None
    notion_mode: Optional[str] = Field(default="per_message")


class NotionTestRequest(BaseModel):
    api_key: str
    dest_type: str
    parent_id: str


class ConfigPayload(BaseModel):
    config: Dict[str, Any]


class NotionSearchRequest(BaseModel):
    api_key: str
    query: str
    type: Optional[str] = Field(default=None, description="database|page|all")


class SlackChannelsRequest(BaseModel):
    token: str
    query: Optional[str] = None
    limit: int = 500


class DiscordTestRequest(BaseModel):
    token: str


class DiscordChannelsRequest(BaseModel):
    token: str
    guild_id: str
    query: Optional[str] = None


class DiscordExtractRequest(BaseModel):
    token: str
    channel: str  # channel id or URL
    out: Optional[str] = None
    format: Optional[str] = None
    reverse: bool = True
    resume: bool = True
    limit: Optional[int] = None
    media_dir: Optional[str] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    only_media: bool = False
    only_text: bool = False
    keywords: Optional[list[str]] = None
    users: Optional[list[str]] = None
    notion_api_key: Optional[str] = None
    notion_dest_type: Optional[str] = None
    notion_parent_id: Optional[str] = None
    notion_mode: Optional[str] = Field(default="per_message")


class TaskState:
    def __init__(self):
        self.status = "running"  # running|done|error
        self.logs: list[str] = []
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.started_at = time.time()
        self.finished_at: Optional[float] = None

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")


tasks: Dict[str, TaskState] = {}

app = FastAPI(title="ChatTools Exporter API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return load_config()


@app.post("/api/config")
def set_config(body: ConfigPayload):
    save_config(body.config)
    return {"saved": True}


@app.post("/api/telegram/login/start")
async def telegram_login_start(req: TelegramLoginStart):
    session = req.session or DEFAULT_SESSION
    if TelegramClient is None:
        raise HTTPException(status_code=500, detail="Telethon not available")
    try:
        cmd = [sys.executable, "-m", "chattools_exporter.tg_login_helper", "start",
               "--api-id", str(req.api_id), "--api-hash", req.api_hash,
               "--phone", req.phone, "--session", session]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "Login start failed")
        return {"ok": True, "code_required": True, "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/telegram/login/complete")
async def telegram_login_complete(req: TelegramLoginComplete):
    session = req.session or DEFAULT_SESSION
    if TelegramClient is None:
        raise HTTPException(status_code=500, detail="Telethon not available")
    try:
        cmd = [sys.executable, "-m", "chattools_exporter.tg_login_helper", "complete",
               "--api-id", str(req.api_id), "--api-hash", req.api_hash,
               "--phone", req.phone, "--session", session,
               "--code", req.code or ""]
        if req.password:
            cmd += ["--password", req.password]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "Login complete failed")
        return {"ok": True, "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _run_task(task: TaskState, target, kwargs):
    try:
        def on_progress(msg: str):
            task.log(msg)

        if "on_progress" in kwargs:
            kwargs["on_progress"] = on_progress
        else:
            kwargs.update({"on_progress": on_progress})
        result = target(**kwargs)
        task.result = result
        task.status = "done"
    except Exception as e:
        task.error = str(e)
        task.status = "error"
    finally:
        task.finished_at = time.time()


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "status": t.status,
        "logs": t.logs[-500:],  # limit
        "result": t.result,
        "error": t.error,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
    }


@app.post("/api/telegram/extract")
def telegram_extract(req: TelegramExtractRequest):
    out_fmt = req.format
    out_path = req.out
    sink = None
    if req.notion_api_key and req.notion_parent_id and req.notion_dest_type:
        sink = notion_sink(req.notion_api_key, req.notion_dest_type, req.notion_parent_id, mode=(req.notion_mode or "per_message"), on_progress=None)
        # When using Notion sink, ignore filesystem out unless provided for logging
        if not out_fmt:
            out_fmt = "jsonl"  # dummy for control flow
        if not out_path:
            out_path = os.path.join(APP_DIR, "_notion_sink.jsonl")
    if not sink:
        # Filesystem mode requires out + format
        if not out_path:
            raise HTTPException(status_code=400, detail="Missing 'out' path for filesystem export")
        if not out_fmt:
            # detect by extension
            ext = os.path.splitext(out_path)[1].lower()
            if ext == ".jsonl":
                out_fmt = "jsonl"
            elif ext == ".csv":
                out_fmt = "csv"
            else:
                raise HTTPException(status_code=400, detail="Provide 'format' or use .jsonl/.csv extension")

    session = req.session or DEFAULT_SESSION
    task_id = str(uuid.uuid4())
    task = TaskState()
    tasks[task_id] = task

    def runner():
        # Filesystem exports: use subprocess CLI for robustness
        if sink is None:
            cmd = [sys.executable, '-m', 'chattools_exporter.export_telegram',
                   '--api-id', str(req.api_id), '--api-hash', req.api_hash,
                   '--session', session,
                   '--chat', req.chat,
                   '--out', out_path]
            if out_fmt:
                cmd += ['--format', out_fmt]
            if req.reverse:
                cmd += ['--reverse']
            if req.resume:
                cmd += ['--resume']
            if req.limit:
                cmd += ['--limit', str(req.limit)]
            if req.media_dir:
                cmd += ['--media-dir', req.media_dir]
            if req.min_date:
                cmd += ['--min-date', req.min_date]
            if req.max_date:
                cmd += ['--max-date', req.max_date]
            if req.only_media:
                cmd += ['--only-media']
            if req.only_text:
                cmd += ['--only-text']
            if req.keywords:
                cmd += ['--keywords', ','.join(req.keywords)]
            if req.users:
                cmd += ['--users', ','.join(req.users)]

            try:
                task.log('Starting Telegram export...')
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                # Stream stderr (progress) and stdout (not much) to logs
                while True:
                    line = proc.stderr.readline()
                    if line:
                        task.log(line.strip())
                    if proc.poll() is not None:
                        # Drain remaining
                        for rem in proc.stderr.readlines():
                            task.log(rem.strip())
                        break
                rc = proc.returncode
                if rc != 0:
                    task.error = f"Exporter exited with code {rc}"
                    task.status = 'error'
                else:
                    # We can't know exact count reliably; report success
                    task.result = {"messages": None}
                    task.status = 'done'
            except Exception as e:
                task.error = str(e)
                task.status = 'error'
            finally:
                task.finished_at = time.time()
            return

        # Notion sink path (requires Telethon in-process)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass
        def on_progress(msg: str):
            task.log(msg)
        try:
            count = tg_export(
                api_id=req.api_id,
                api_hash=req.api_hash,
                session=session,
                chat=req.chat,
                out_path=out_path,
                out_fmt=out_fmt,
                reverse=req.reverse,
                resume=req.resume,
                limit=req.limit,
                media_dir=req.media_dir,
                min_date=req.min_date,
                max_date=req.max_date,
                only_media=req.only_media,
                only_text=req.only_text,
                keywords=req.keywords or [],
                users=req.users or [],
                on_progress=on_progress,
                sink=sink,
            )
            if sink and hasattr(sink, 'finalize'):
                try:
                    sink.finalize(chat_title=None)
                except Exception as e:
                    task.log(f"Notion finalize error: {e}")
            task.result = {"messages": count}
            task.status = 'done'
        except Exception as e:
            task.error = str(e)
            task.status = 'error'
        finally:
            task.finished_at = time.time()
            try:
                loop.close()
            except Exception:
                pass

    threading.Thread(target=runner, daemon=True).start()
    return {"task_id": task_id}


@app.post("/api/slack/test")
def slack_test(body: Dict[str, str]):
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    try:
        msg = test_slack_token(token)
        return {"ok": True, "message": msg}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/notion/test")
def notion_test_endpoint(req: NotionTestRequest):
    try:
        msg = notion_test(req.api_key, req.dest_type, req.parent_id)
        return {"ok": True, "message": msg}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/notion/search")
def notion_search(req: NotionSearchRequest):
    from .notion_writer import NotionClient
    try:
        client = NotionClient(req.api_key)
        f = None
        if req.type and req.type.lower() in ("database", "page"):
            f = req.type.lower()
        res = client.search(req.query, filter_object=f)
        items = []
        for r in res.get("results", []):
            obj = r.get("object")
            rid = r.get("id")
            title = ""
            if obj == "database":
                title = "".join([t.get("plain_text", "") for t in r.get("title", [])]) or "(untitled database)"
                items.append({"type": "Database", "id": rid, "title": title})
            elif obj == "page":
                props = r.get("properties", {})
                tname = None
                for name, meta in props.items():
                    if meta.get("type") == "title":
                        tname = name
                        break
                if tname:
                    title_arr = props[tname].get("title", [])
                    title = "".join([t.get("plain_text", "") for t in title_arr]) or "(untitled page)"
                else:
                    title = "(page)"
                items.append({"type": "Page", "id": rid, "title": title})
        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/slack/extract")
def slack_extract(req: SlackExtractRequest):
    out_fmt = req.format
    out_path = req.out
    sink = None
    if req.notion_api_key and req.notion_parent_id and req.notion_dest_type:
        sink = notion_sink(req.notion_api_key, req.notion_dest_type, req.notion_parent_id, mode=(req.notion_mode or "per_message"), on_progress=None)
        if not out_fmt:
            out_fmt = "jsonl"
        if not out_path:
            out_path = os.path.join(APP_DIR, "_notion_sink_slack.jsonl")
    if not sink:
        if not out_path:
            raise HTTPException(status_code=400, detail="Missing 'out' path for filesystem export")
        if not out_fmt:
            ext = os.path.splitext(out_path)[1].lower()
            if ext == ".jsonl":
                out_fmt = "jsonl"
            elif ext == ".csv":
                out_fmt = "csv"
            else:
                raise HTTPException(status_code=400, detail="Provide 'format' or use .jsonl/.csv extension")

    task_id = str(uuid.uuid4())
    task = TaskState()
    tasks[task_id] = task

    def runner():
        kwargs = dict(
            token=req.token,
            channel=req.channel,
            out_path=out_path,
            out_fmt=out_fmt,
            reverse=req.reverse,
            resume=req.resume,
            limit=req.limit,
            media_dir=req.media_dir,
            min_date=req.min_date,
            max_date=req.max_date,
            only_media=req.only_media,
            only_text=req.only_text,
            keywords=req.keywords or [],
            users=req.users or [],
            sink=sink,
        )

        def on_progress(msg: str):
            task.log(msg)

        try:
            kwargs["on_progress"] = on_progress
            count = slack_export(**kwargs)
            try:
                if sink and hasattr(sink, "finalize"):
                    sink.finalize(chat_title=None)
            except Exception as e:
                task.log(f"Notion finalize error: {e}")
            task.result = {"messages": count}
            task.status = "done"
        except Exception as e:
            task.error = str(e)
            task.status = "error"
        finally:
            task.finished_at = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return {"task_id": task_id}


@app.post("/api/slack/channels")
def slack_channels(req: SlackChannelsRequest):
    from slack_sdk import WebClient
    client = WebClient(token=req.token)
    q = (req.query or "").lower()
    items = []
    cursor = None
    cap = 0
    while True and cap < req.limit:
        res = client.conversations_list(limit=200, cursor=cursor, types="public_channel,private_channel")
        for c in res.get("channels", []):
            name = c.get("name") or ""
            if not q or q in name.lower():
                items.append({"id": c.get("id"), "name": name, "is_private": c.get("is_private", False)})
                cap += 1
                if cap >= req.limit:
                    break
        if cap >= req.limit:
            break
        cursor = res.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break
    return {"results": items}


@app.post("/api/discord/test")
def discord_test(req: DiscordTestRequest):
    # GET /users/@me with bot token
    import requests
    r = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": f"Bot {req.token}", "User-Agent": "ChatTools-Exporter"}, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Discord API error: {r.status_code} {r.text}")
    u = r.json() or {}
    return {"ok": True, "bot_id": u.get("id"), "username": u.get("username")}


@app.post("/api/discord/channels")
def discord_channels(req: DiscordChannelsRequest):
    import requests
    r = requests.get(f"https://discord.com/api/v10/guilds/{req.guild_id}/channels", headers={"Authorization": f"Bot {req.token}", "User-Agent": "ChatTools-Exporter"}, timeout=30)
    if r.status_code == 403:
        raise HTTPException(status_code=403, detail="Forbidden: bot likely missing permissions or not in guild")
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Discord API error: {r.status_code} {r.text}")
    chans = r.json() or []
    items = []
    q = (req.query or '').lower()
    for c in chans:
        # type 0 = text channel
        if c.get('type') == 0:
            name = c.get('name') or ''
            if not q or q in name.lower():
                items.append({"id": c.get('id'), "name": name})
    return {"results": items}


@app.post("/api/discord/extract")
def discord_extract(req: DiscordExtractRequest):
    out_fmt = req.format
    out_path = req.out
    sink = None
    if req.notion_api_key and req.notion_parent_id and req.notion_dest_type:
        sink = notion_sink(req.notion_api_key, req.notion_dest_type, req.notion_parent_id, mode=(req.notion_mode or "per_message"), on_progress=None)
        if not out_fmt:
            out_fmt = "jsonl"
        if not out_path:
            out_path = os.path.join(APP_DIR, "_notion_sink_discord.jsonl")
    if not sink:
        if not out_path:
            raise HTTPException(status_code=400, detail="Missing 'out' path for filesystem export")
        if not out_fmt:
            ext = os.path.splitext(out_path)[1].lower()
            if ext == ".jsonl":
                out_fmt = "jsonl"
            elif ext == ".csv":
                out_fmt = "csv"
            else:
                raise HTTPException(status_code=400, detail="Provide 'format' or use .jsonl/.csv extension")

    task_id = str(uuid.uuid4())
    task = TaskState()
    tasks[task_id] = task

    def runner():
        if sink is None:
            # Use subprocess CLI for file exports
            cmd = [sys.executable, '-m', 'chattools_exporter.export_discord',
                   '--token', req.token, '--channel', req.channel,
                   '--out', out_path]
            if out_fmt:
                cmd += ['--format', out_fmt]
            if req.reverse:
                cmd += ['--reverse']
            if req.resume:
                cmd += ['--resume']
            if req.limit:
                cmd += ['--limit', str(req.limit)]
            if req.media_dir:
                cmd += ['--media-dir', req.media_dir]
            if req.min_date:
                cmd += ['--min-date', req.min_date]
            if req.max_date:
                cmd += ['--max-date', req.max_date]
            if req.only_media:
                cmd += ['--only-media']
            if req.only_text:
                cmd += ['--only-text']
            if req.keywords:
                cmd += ['--keywords', ','.join(req.keywords)]
            if req.users:
                cmd += ['--users', ','.join(req.users)]
            try:
                task.log('Starting Discord export...')
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                while True:
                    line = proc.stderr.readline()
                    if line:
                        task.log(line.strip())
                    if proc.poll() is not None:
                        for rem in proc.stderr.readlines():
                            task.log(rem.strip())
                        break
                rc = proc.returncode
                if rc != 0:
                    task.error = f"Exporter exited with code {rc}"
                    task.status = 'error'
                else:
                    task.result = {"messages": None}
                    task.status = 'done'
            except Exception as e:
                task.error = str(e)
                task.status = 'error'
            finally:
                task.finished_at = time.time()
            return

        # Notion sink path (in-process)
        def on_progress(msg: str):
            task.log(msg)
        try:
            count = discord_export(
                token=req.token,
                channel=req.channel,
                out_path=out_path,
                out_fmt=out_fmt,
                reverse=req.reverse,
                resume=req.resume,
                limit=req.limit,
                media_dir=req.media_dir,
                min_date=req.min_date,
                max_date=req.max_date,
                only_media=req.only_media,
                only_text=req.only_text,
                keywords=req.keywords or [],
                users=req.users or [],
                on_progress=on_progress,
                sink=sink,
            )
            if sink and hasattr(sink, 'finalize'):
                try:
                    sink.finalize(chat_title=None)
                except Exception as e:
                    task.log(f"Notion finalize error: {e}")
            task.result = {"messages": count}
            task.status = 'done'
        except Exception as e:
            task.error = str(e)
            task.status = 'error'
        finally:
            task.finished_at = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return {"task_id": task_id}


# Convenience for `python -m chattools_exporter.server`
def main():
    import uvicorn

    port = int(os.getenv("EXPORTER_PORT", "8000"))
    uvicorn.run("chattools_exporter.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()

# Mount static frontend if built
WEB_DIST = os.path.abspath(os.path.join(APP_DIR, "..", "..", "web", "dist"))
if os.path.isdir(WEB_DIST):
    app.mount("/app", StaticFiles(directory=WEB_DIST, html=True), name="web")

    @app.get("/app/{full_path:path}")
    def spa_fallback(full_path: str):
        index_path = os.path.join(WEB_DIST, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Not Found")
