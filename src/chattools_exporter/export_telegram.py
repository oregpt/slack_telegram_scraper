import os
import sys
import json
import csv
import argparse
from datetime import datetime

from telethon.sync import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


def parse_args():
    p = argparse.ArgumentParser(description="Export Telegram group/channel messages")
    p.add_argument("--api-id", type=int, default=int(os.getenv("TELEGRAM_API_ID", "0")), help="Telegram API ID")
    p.add_argument("--api-hash", default=os.getenv("TELEGRAM_API_HASH"), help="Telegram API Hash")
    p.add_argument("--session", default="tg_export.session", help="Session file name")
    p.add_argument("--chat", required=True, help="Chat username/link/id (e.g., @group, https://t.me/group, or -100123...)")
    p.add_argument("--out", required=True, help="Output file path (jsonl or csv)")
    p.add_argument("--format", choices=["jsonl", "csv"], default=None, help="Output format (defaults from file extension)")
    p.add_argument("--reverse", action="store_true", help="Oldest to newest (recommended for stable resume)")
    p.add_argument("--resume", action="store_true", help="Resume from last saved message id (jsonl only)")
    p.add_argument("--limit", type=int, default=None, help="Limit number of messages to export")
    p.add_argument("--media-dir", default=None, help="Directory to download media into (optional)")
    p.add_argument("--min-date", default=None, help="Only messages on/after this date (YYYY-MM-DD)")
    p.add_argument("--max-date", default=None, help="Only messages on/before this date (YYYY-MM-DD)")
    p.add_argument("--only-media", action="store_true", help="Only export messages that contain media")
    p.add_argument("--only-text", action="store_true", help="Only export messages without media")
    p.add_argument("--keywords", default=None, help="Comma-separated keywords (case-insensitive) to match in text")
    p.add_argument("--users", default=None, help="Comma-separated usernames (without @) or numeric IDs to include")
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


def read_last_id_jsonl(path):
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


def parse_date(d):
    if not d:
        return None
    return datetime.strptime(d, "%Y-%m-%d")


def msg_to_row(m, chat_title):
    sender = None
    sender_id = None
    sender_username = None
    if getattr(m, "sender", None):
        s = m.sender
        sender_id = getattr(s, "id", None)
        sender_username = getattr(s, "username", None)
        name_parts = [getattr(s, "first_name", None), getattr(s, "last_name", None)]
        sender = " ".join([x for x in name_parts if x]) or sender_username or str(sender_id)

    text = m.message or ""
    reply_to = m.reply_to_msg_id if hasattr(m, "reply_to_msg_id") else None
    views = getattr(m, "views", None)
    forwards = getattr(m, "forwards", None)
    edit_date = m.edit_date.isoformat() if m.edit_date else None
    via_bot_id = getattr(m, "via_bot_id", None)
    is_pinned = bool(getattr(m, "pinned", False))

    media = None
    media_type = None
    file_name = None
    if m.media:
        media = True
        if isinstance(m.media, MessageMediaPhoto):
            media_type = "photo"
        elif isinstance(m.media, MessageMediaDocument):
            media_type = "document"
            doc = getattr(m.media, "document", None)
            if doc and getattr(doc, "attributes", None):
                for attr in doc.attributes:
                    fn = getattr(attr, "file_name", None)
                    if fn:
                        file_name = fn
                        break
        else:
            media_type = type(m.media).__name__

    return {
        "id": m.id,
        "date": m.date.isoformat(),
        "chat_id": m.chat_id,
        "chat_title": chat_title,
        "sender_id": sender_id,
        "sender_username": sender_username,
        "sender_display": sender,
        "text": text,
        "reply_to_id": reply_to,
        "views": views,
        "forwards": forwards,
        "edit_date": edit_date,
        "via_bot_id": via_bot_id,
        "is_pinned": is_pinned,
        "media": bool(media),
        "media_type": media_type,
        "media_file_name": file_name,
    }


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def export_messages(
    api_id: int,
    api_hash: str,
    session: str,
    chat: str,
    out_path: str,
    out_fmt: str,
    reverse: bool = True,
    resume: bool = False,
    limit: int | None = None,
    media_dir: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
    only_media: bool = False,
    only_text: bool = False,
    keywords: list[str] | None = None,
    users: list[str] | None = None,
    on_progress=None,
    sink=None,
):
    if media_dir and not sink:
        # Only ensure local media directory when writing to filesystem
        ensure_dir(media_dir)

    min_dt = parse_date(min_date)
    max_dt = parse_date(max_date)
    last_id = None
    if resume and out_fmt == "jsonl" and os.path.exists(out_path):
        last_id = read_last_id_jsonl(out_path)
        if last_id and on_progress:
            on_progress(f"Resuming after message id {last_id}")

    kw_list = [k.strip().lower() for k in (keywords or []) if k.strip()]
    user_list = [u.strip().lstrip("@") for u in (users or []) if u.strip()]

    with TelegramClient(session, api_id, api_hash) as client:
        entity = client.get_entity(chat)
        chat_title = getattr(entity, "title", getattr(entity, "username", str(getattr(entity, "id", ""))))

        # Prepare writers (filesystem only)
        out_f = None
        csv_writer = None
        if sink is None:
            if out_fmt == "jsonl":
                out_f = open(out_path, "a", encoding="utf-8")
            else:
                out_f = open(out_path, "a", newline="", encoding="utf-8")
                headers = [
                    "id","date","chat_id","chat_title","sender_id","sender_username",
                    "sender_display","text","reply_to_id","views","forwards","edit_date",
                    "via_bot_id","is_pinned","media","media_type","media_file_name"
                ]
                csv_writer = csv.DictWriter(out_f, fieldnames=headers)
                if out_f.tell() == 0:
                    csv_writer.writeheader()

        count = 0
        try:
            it = client.iter_messages(
                entity,
                reverse=reverse,
                limit=limit,
                min_id=(last_id + 1) if last_id else 0,
            )
            for m in it:
                # Date filters
                if min_dt and m.date.replace(tzinfo=None) < min_dt:
                    continue
                if max_dt and m.date.replace(tzinfo=None) > max_dt:
                    continue

                # Media filters
                if only_media and not m.media:
                    continue
                if only_text and m.media:
                    continue

                # User filters
                if user_list:
                    uid = str(getattr(m.sender, "id", "")) if getattr(m, "sender", None) else ""
                    uname = (getattr(m.sender, "username", None) or "").lower() if getattr(m, "sender", None) else ""
                    if uid not in user_list and (uname not in [u.lower() for u in user_list]):
                        continue

                # Keyword filters
                if kw_list:
                    text = (m.message or "").lower()
                    if not any(k in text for k in kw_list):
                        continue

                row = msg_to_row(m, chat_title)

                # Optionally download media (only for filesystem exports)
                if media_dir and m.media and sink is None:
                    try:
                        path = client.download_media(m, file=media_dir)
                        row["media_path"] = path
                    except FloodWaitError as e:
                        if on_progress:
                            on_progress(f"Rate limited during media download, sleeping {e.seconds}s...")
                        import time
                        time.sleep(e.seconds)
                        path = client.download_media(m, file=media_dir)
                        row["media_path"] = path
                    except Exception as e:
                        row["media_path"] = None
                        if on_progress:
                            on_progress(f"Media download failed for {m.id}: {e}")

                if sink is not None:
                    try:
                        sink(row, m, client)
                    except Exception as e:
                        if on_progress:
                            on_progress(f"Sink error for message {m.id}: {e}")
                else:
                    if out_fmt == "jsonl":
                        out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    else:
                        csv_writer.writerow(row)

                count += 1
                if count % 500 == 0:
                    out_f.flush()
                    if on_progress:
                        on_progress(f"Exported {count} messages...")

        finally:
            if out_f:
                out_f.flush()
                out_f.close()

        if on_progress:
            on_progress(f"Done. Exported {count} messages to {out_path}")
    return count


def main():
    args = parse_args()
    out_fmt = detect_format(args.out, args.format)

    if not args.api_id or not args.api_hash:
        print("Error: Provide --api-id and --api-hash or set TELEGRAM_API_ID/TELEGRAM_API_HASH", file=sys.stderr)
        sys.exit(1)

    kw = [x for x in (args.keywords.split(",") if args.keywords else [])]
    users = [x for x in (args.users.split(",") if args.users else [])]

    export_messages(
        api_id=args.api_id,
        api_hash=args.api_hash,
        session=args.session,
        chat=args.chat,
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
