import os
import sys
import json
import csv
import time
import argparse
import datetime as dt
from typing import Optional, List

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import requests


def parse_args():
    p = argparse.ArgumentParser(description="Export Slack channel messages")
    p.add_argument("--token", default=os.getenv("SLACK_TOKEN"), help="Slack Bot/User OAuth token (env SLACK_TOKEN)")
    p.add_argument("--channel", required=True, help="Channel name (#general) or channel ID (C.../G...)")
    p.add_argument("--out", required=True, help="Output file path (jsonl or csv)")
    p.add_argument("--format", choices=["jsonl", "csv"], default=None, help="Output format (defaults from file extension)")
    p.add_argument("--reverse", action="store_true", help="Oldest to newest (will sort by timestamp)")
    p.add_argument("--resume", action="store_true", help="Resume from last saved timestamp (jsonl only)")
    p.add_argument("--limit", type=int, default=None, help="Max messages to export")
    p.add_argument("--media-dir", default=None, help="Directory to download files (optional)")
    p.add_argument("--min-date", default=None, help="Only messages on/after this date (YYYY-MM-DD)")
    p.add_argument("--max-date", default=None, help="Only messages on/before this date (YYYY-MM-DD)")
    p.add_argument("--only-media", action="store_true", help="Only export messages with files")
    p.add_argument("--only-text", action="store_true", help="Only export messages without files")
    p.add_argument("--keywords", default=None, help="Comma-separated keywords (case-insensitive) to match in text")
    p.add_argument("--users", default=None, help="Comma-separated user IDs or display names to include")
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


def to_ts(d: Optional[dt.datetime]) -> Optional[float]:
    if not d:
        return None
    return d.replace(tzinfo=dt.timezone.utc).timestamp()


def read_last_ts_jsonl(path: str) -> Optional[str]:
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
    return (last or {}).get("ts")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def get_channel_id(client: WebClient, channel_input: str) -> str:
    ch = channel_input.strip()
    if ch.startswith("C") or ch.startswith("G"):
        return ch
    if ch.startswith("#"):
        ch = ch[1:]
    def try_list(types: str):
        cursor = None
        while True:
            res = client.conversations_list(limit=1000, cursor=cursor, types=types)
            for c in res.get("channels", []):
                if c.get("name") == ch:
                    return c.get("id")
            cursor = res.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
        return None

    # Try both public and private; if missing scope, fall back to public only
    try:
        found = try_list("public_channel,private_channel")
    except SlackApiError as e:
        if e.response and e.response.get("error") == "missing_scope":
            found = try_list("public_channel")
        else:
            raise
    if found:
        return found
    raise ValueError(f"Channel not found: {channel_input}")


def slack_ts_to_iso(ts: str) -> str:
    try:
        seconds = float(ts)
        return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).isoformat()
    except Exception:
        return ts


def msg_to_row(m: dict, channel_id: str, channel_name: str) -> dict:
    text = m.get("text", "")
    files = m.get("files", []) or []
    media = bool(files)
    media_types = ",".join([f.get("filetype") or f.get("mimetype", "") for f in files if isinstance(f, dict)]) or None
    file_names = ";".join([f.get("name", "") for f in files if isinstance(f, dict)]) or None

    return {
        "id": m.get("client_msg_id") or m.get("ts"),
        "ts": m.get("ts"),
        "date": slack_ts_to_iso(m.get("ts", "")),
        "chat_id": channel_id,
        "chat_title": channel_name,
        "sender_id": m.get("user") or m.get("bot_id"),
        "sender_username": m.get("username"),
        "sender_display": m.get("user_profile", {}).get("real_name") if isinstance(m.get("user_profile"), dict) else None,
        "text": text,
        "reply_to_id": None,
        "views": None,
        "forwards": None,
        "edit_date": slack_ts_to_iso(m.get("edited", {}).get("ts")) if isinstance(m.get("edited"), dict) else None,
        "via_bot_id": m.get("bot_id"),
        "is_pinned": False,
        "media": media,
        "media_type": media_types,
        "media_file_name": file_names,
    }


def download_files(files: List[dict], token: str, media_dir: str):
    paths = []
    headers = {"Authorization": f"Bearer {token}"}
    for f in files:
        url = f.get("url_private")
        if not url:
            continue
        name = f.get("name") or f.get("id") or f"file_{int(time.time())}"
        dest = os.path.join(media_dir, name)
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            with open(dest, "wb") as out:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        out.write(chunk)
            paths.append(dest)
        except Exception:
            continue
    return paths


def export_slack_messages(
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
    client = WebClient(token=token)

    if media_dir and not sink:
        ensure_dir(media_dir)

    min_dt = parse_date(min_date)
    max_dt = parse_date(max_date)
    oldest = to_ts(min_dt)
    latest = to_ts(max_dt)

    last_ts = None
    if resume and out_fmt == "jsonl" and os.path.exists(out_path):
        last_ts = read_last_ts_jsonl(out_path)
        if last_ts and on_progress:
            on_progress(f"Resuming after ts {last_ts}")
        if last_ts:
            try:
                v = float(last_ts)
                oldest = max(oldest or 0.0, v)
            except Exception:
                pass

    channel_id = get_channel_id(client, channel)
    channel_name = channel.lstrip("#")
    # Try fetch channel info to get name
    try:
        info = client.conversations_info(channel=channel_id)
        channel_name = info.get("channel", {}).get("name") or channel_name
    except SlackApiError:
        pass

    # Prepare writers
    out_f = None
    csv_writer = None
    if sink is None:
        if out_fmt == "jsonl":
            out_f = open(out_path, "a", encoding="utf-8")
        else:
            out_f = open(out_path, "a", newline="", encoding="utf-8")
            headers = [
                "id","ts","date","chat_id","chat_title","sender_id","sender_username",
                "sender_display","text","reply_to_id","views","forwards","edit_date",
                "via_bot_id","is_pinned","media","media_type","media_file_name","media_path"
            ]
            csv_writer = csv.DictWriter(out_f, fieldnames=headers)
            if out_f.tell() == 0:
                csv_writer.writeheader()

    count = 0
    collected = [] if reverse else None

    cursor = None
    while True:
        try:
            res = client.conversations_history(
                channel=channel_id,
                limit=1000,
                cursor=cursor,
                oldest=str(oldest) if oldest else None,
                latest=str(latest) if latest else None,
                inclusive=False,
            )
        except SlackApiError as e:
            raise RuntimeError(f"Slack API error: {e.response['error']}")
        msgs = res.get("messages", [])
        if not msgs:
            break

        for m in msgs:
            if limit and count >= limit:
                break

            # Filters
            files = m.get("files", []) or []
            if only_media and not files:
                continue
            if only_text and files:
                continue

            if users:
                uid = m.get("user") or m.get("bot_id") or ""
                uname = (m.get("username") or "").lower()
                if uid not in users and uname not in [u.lower() for u in users]:
                    continue

            if keywords:
                text = (m.get("text") or "").lower()
                if not any(k.lower() in text for k in keywords):
                    continue

            row = msg_to_row(m, channel_id, channel_name)

            # Download files if requested (filesystem only)
            if media_dir and files and sink is None:
                paths = download_files(files, token, media_dir)
                row["media_path"] = ";".join(paths) if paths else None

            if reverse:
                collected.append(row)
            else:
                if sink is not None:
                    sink(row, m, client)
                else:
                    if out_fmt == "jsonl":
                        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    else:
                        csv_writer.writerow(row)
            count += 1
        if limit and count >= limit:
            break
        cursor = res.get("response_metadata", {}).get("next_cursor") or None
        if not cursor:
            break

    # Flush collected in ascending order by ts
    if reverse and collected:
        try:
            collected.sort(key=lambda r: float(r.get("ts", "0")))
        except Exception:
            collected.sort(key=lambda r: r.get("ts", ""))
        for row in collected:
            if sink is not None:
                sink(row, None, client)
            else:
                if out_fmt == "jsonl":
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                else:
                    csv_writer.writerow(row)

    if out_f:
        out_f.flush(); out_f.close()
    if on_progress:
        on_progress(f"Done. Exported {count} messages to {out_path}")
    return count


def test_slack_token(token: str) -> str:
    client = WebClient(token=token)
    res = client.auth_test()
    user = res.get("user") or res.get("user_id")
    team = res.get("team") or res.get("team_id")
    return f"Token OK: user={user}, team={team}"


def main():
    args = parse_args()
    out_fmt = detect_format(args.out, args.format)

    if not args.token:
        print("Error: Provide --token or set SLACK_TOKEN", file=sys.stderr)
        sys.exit(1)

    kw = [x.strip() for x in (args.keywords.split(",") if args.keywords else []) if x.strip()]
    users = [x.strip() for x in (args.users.split(",") if args.users else []) if x.strip()]

    export_slack_messages(
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
