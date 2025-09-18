import os
import sys
import json
import csv
import argparse
import time
import datetime as dt
from typing import Optional, List, Dict, Any

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Export Discord channel messages (bot token)")
    p.add_argument("--token", required=True, help="Discord Bot token")
    p.add_argument("--channel", required=True, help="Channel ID or channel URL (https://discord.com/channels/<guild>/<channel>)")
    p.add_argument("--out", required=True, help="Output file path (jsonl or csv)")
    p.add_argument("--format", choices=["jsonl", "csv"], default=None, help="Output format (defaults from file extension)")
    p.add_argument("--reverse", action="store_true", help="Oldest to newest (collect then sort)")
    p.add_argument("--resume", action="store_true", help="Resume from last saved message id (jsonl only)")
    p.add_argument("--limit", type=int, default=None, help="Max messages to export")
    p.add_argument("--media-dir", default=None, help="Directory to download attachments (optional)")
    p.add_argument("--min-date", default=None, help="Only messages on/after this date (YYYY-MM-DD)")
    p.add_argument("--max-date", default=None, help="Only messages on/before this date (YYYY-MM-DD)")
    p.add_argument("--only-media", action="store_true", help="Only export messages with attachments")
    p.add_argument("--only-text", action="store_true", help="Only export messages without attachments")
    p.add_argument("--keywords", default=None, help="Comma-separated keywords (case-insensitive) to match in content")
    p.add_argument("--users", default=None, help="Comma-separated user IDs or usernames to include")
    return p.parse_args()


def detect_format(path, cli_format):
    if cli_format:
        return cli_format
    ext = os.path.splitext(path)[1].lower()
    if ext == ".jsonl":
        return "jsonl"
    if ext == ".csv":
        return "csv"
    raise ValueError("Please provide --format or use .jsonl/.csv extension")


def parse_date(d: Optional[str]) -> Optional[dt.datetime]:
    if not d:
        return None
    return dt.datetime.strptime(d, "%Y-%m-%d")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def read_last_id_jsonl(path: str) -> Optional[str]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    last = None
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block = 4096
        data = b""
        while size > 0:
            seek = max(0, size - block)
            f.seek(seek)
            chunk = f.read(size - seek)
            data = chunk + data
            size = seek
            if b"\n" in data:
                break
        lines = data.splitlines()
        for line in reversed(lines):
            if line.strip():
                try:
                    last = json.loads(line.decode("utf-8", errors="ignore"))
                    break
                except Exception:
                    continue
    return (last or {}).get("id")


def iso(ts: str) -> str:
    # Discord timestamps are ISO already, but ensure normalization
    try:
        return dt.datetime.fromisoformat(ts.replace('Z', '+00:00')).isoformat()
    except Exception:
        return ts


def msg_to_row(m: Dict[str, Any], channel_id: str, channel_name: Optional[str]) -> Dict[str, Any]:
    author = m.get("author", {}) if isinstance(m.get("author"), dict) else {}
    content = m.get("content", "")
    attachments = m.get("attachments", []) or []
    media = bool(attachments)
    media_types = ",".join([att.get("content_type") or att.get("filename", "") for att in attachments if isinstance(att, dict)]) or None
    media_names = ";".join([att.get("filename", "") for att in attachments if isinstance(att, dict)]) or None

    return {
        "id": m.get("id"),
        "date": iso(m.get("timestamp", "")),
        "chat_id": channel_id,
        "chat_title": channel_name,
        "sender_id": author.get("id"),
        "sender_username": author.get("username"),
        "sender_display": author.get("global_name") or author.get("username"),
        "text": content,
        "reply_to_id": None,  # could parse from message references
        "views": None,
        "forwards": None,
        "edit_date": iso(m.get("edited_timestamp")) if m.get("edited_timestamp") else None,
        "via_bot_id": None,
        "is_pinned": bool(m.get("pinned")),
        "media": media,
        "media_type": media_types,
        "media_file_name": media_names,
    }


def download_attachments(att: List[Dict[str, Any]], media_dir: str) -> List[str]:
    ensure_dir(media_dir)
    paths = []
    for a in att:
        url = a.get("url")
        if not url:
            continue
        name = a.get("filename") or f"file_{int(time.time())}"
        dest = os.path.join(media_dir, name)
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            out.write(chunk)
            paths.append(dest)
        except Exception:
            continue
    return paths


def parse_channel_id(input_str: str) -> str:
    s = input_str.strip()
    if s.startswith("http") and "/channels/" in s:
        try:
            parts = s.split("/channels/")[1].split("/")
            # guild_id = parts[0]
            channel_id = parts[1]
            return channel_id
        except Exception:
            pass
    return s


def export_discord_messages(
    token: str,
    channel: str,
    out_path: str,
    out_fmt: str,
    reverse: bool = True,
    resume: bool = False,
    limit: Optional[int] = None,
    media_dir: Optional[str] = None,
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
    only_media: bool = False,
    only_text: bool = False,
    keywords: Optional[List[str]] = None,
    users: Optional[List[str]] = None,
    on_progress=None,
    sink=None,
):
    channel_id = parse_channel_id(channel)
    headers = {"Authorization": f"Bot {token}", "User-Agent": "ChatTools-Exporter"}
    base = "https://discord.com/api/v10"

    # Get channel name
    channel_name = None
    try:
        info = requests.get(f"{base}/channels/{channel_id}", headers=headers, timeout=30)
        if info.status_code == 200:
            channel_name = (info.json() or {}).get("name")
    except Exception:
        pass

    # Writers
    out_f = None
    csv_writer = None
    if sink is None:
        if out_fmt == "jsonl":
            out_f = open(out_path, "a", encoding="utf-8")
        else:
            out_f = open(out_path, "a", newline="", encoding="utf-8")
            headers_row = [
                "id","date","chat_id","chat_title","sender_id","sender_username",
                "sender_display","text","reply_to_id","views","forwards","edit_date",
                "via_bot_id","is_pinned","media","media_type","media_file_name","media_path"
            ]
            csv_writer = csv.DictWriter(out_f, fieldnames=headers_row)
            if out_f.tell() == 0:
                csv_writer.writeheader()

    min_dt = parse_date(min_date)
    max_dt = parse_date(max_date)
    kw = [k.lower() for k in (keywords or []) if k]
    user_filters = [u.lower() for u in (users or []) if u]

    last_id = None
    if resume and out_fmt == "jsonl" and os.path.exists(out_path):
        last_id = read_last_id_jsonl(out_path)
        if last_id and on_progress:
            on_progress(f"Resuming after id {last_id}")

    collected = [] if reverse else None
    fetched = 0
    params = {"limit": 100}
    if last_id:
        params["after"] = last_id

    while True:
        try:
            r = requests.get(f"{base}/channels/{channel_id}/messages", headers=headers, params=params, timeout=30)
        except Exception as e:
            raise RuntimeError(f"Discord request failed: {e}")
        if r.status_code == 429:
            retry = int(r.headers.get("Retry-After", "1"))
            time.sleep(max(1, retry))
            continue
        if r.status_code == 403:
            raise RuntimeError("Forbidden: bot likely missing Read Message History or access to channel")
        if r.status_code == 401:
            raise RuntimeError("Unauthorized: invalid bot token")
        if r.status_code != 200:
            raise RuntimeError(f"Discord API error: {r.status_code} {r.text}")
        msgs = r.json() or []
        if not msgs:
            break

        # API returns newest-first; process accordingly
        for m in msgs:
            if limit and fetched >= limit:
                break

            # Date filters
            try:
                m_dt = dt.datetime.fromisoformat(m.get("timestamp", "").replace('Z', '+00:00'))
            except Exception:
                m_dt = None
            if min_dt and m_dt and m_dt < min_dt:
                continue
            if max_dt and m_dt and m_dt > max_dt:
                continue

            atts = m.get("attachments", []) or []
            if only_media and not atts:
                continue
            if only_text and atts:
                continue

            if user_filters:
                au = m.get("author", {}) if isinstance(m.get("author"), dict) else {}
                uid = str(au.get("id", "")).lower()
                uname = str(au.get("username", "")).lower()
                if uid not in user_filters and uname not in user_filters:
                    continue

            if kw:
                content = (m.get("content") or "").lower()
                if not any(k in content for k in kw):
                    continue

            row = msg_to_row(m, channel_id, channel_name)
            # Download attachments if requested (filesystem only)
            if media_dir and atts and sink is None:
                paths = download_attachments(atts, media_dir)
                row["media_path"] = ";".join(paths) if paths else None

            if reverse:
                collected.append(row)
            else:
                if sink is not None:
                    sink(row, m, None)
                else:
                    if out_fmt == "jsonl":
                        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    else:
                        csv_writer.writerow(row)
            fetched += 1
        if limit and fetched >= limit:
            break
        # Paginate using 'before' = smallest id we've seen to keep going backwards
        smallest = min(int(m.get("id")) for m in msgs if m.get("id"))
        params = {"limit": 100, "before": str(smallest)}

    if reverse and collected:
        try:
            collected.sort(key=lambda r: int(r.get("id", "0")))
        except Exception:
            collected.sort(key=lambda r: r.get("id", ""))
        for row in collected:
            if sink is not None:
                sink(row, None, None)
            else:
                if out_fmt == "jsonl":
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                else:
                    csv_writer.writerow(row)

    if out_f:
        out_f.flush(); out_f.close()
    if on_progress:
        on_progress(f"Done. Exported {fetched} messages to {out_path}")
    return fetched


def main():
    args = parse_args()
    out_fmt = detect_format(args.out, args.format)
    kw = [x.strip() for x in (args.keywords.split(",") if args.keywords else []) if x.strip()]
    users = [x.strip() for x in (args.users.split(",") if args.users else []) if x.strip()]
    export_discord_messages(
        token=args.token,
        channel=args.channel,
        out_path=args.out,
        out_fmt=out_fmt,
        reverse=args.reverse,
        resume=args.resume,
        limit=args.limit,
        media_dir=args.media_dir,
        min_date=args.min_date,
        max_date=args.max_date,
        only_media=args.only_media,
        only_text=args.only_text,
        keywords=kw,
        users=users,
        on_progress=lambda msg: print(msg, file=sys.stderr),
        sink=None,
    )


if __name__ == "__main__":
    main()

