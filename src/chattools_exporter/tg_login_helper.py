import sys
import argparse
import os

try:
    from telethon.sync import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except Exception as e:
    print(f"ERROR: Telethon not available: {e}", file=sys.stderr)
    sys.exit(2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["start", "complete"])  # start: send code; complete: sign in with code
    p.add_argument("--api-id", type=int, required=True)
    p.add_argument("--api-hash", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--code", default=None)
    p.add_argument("--password", default=None)
    args = p.parse_args()

    if args.action == "start":
        client = TelegramClient(args.session, args.api_id, args.api_hash)
        client.connect()
        try:
            sent = client.send_code_request(args.phone)
            # Try to persist phone_code_hash so we can complete auth later in a separate process
            code_hash = None
            try:
                code_hash = getattr(sent, 'phone_code_hash', None)
            except Exception:
                code_hash = None
            # Fallback: internal map
            if not code_hash:
                try:
                    m = getattr(client, '_phone_code_hash', {})
                    if isinstance(m, dict):
                        code_hash = m.get(args.phone) or (next(iter(m.values())) if m else None)
                except Exception:
                    pass
            if code_hash:
                aux_path = args.session + '.codehash'
                with open(aux_path, 'w', encoding='utf-8') as f:
                    f.write(code_hash)
            print("OK: code sent")
        finally:
            client.disconnect()
        return

    if args.action == "complete":
        client = TelegramClient(args.session, args.api_id, args.api_hash)
        client.connect()
        try:
            phone_code_hash = None
            aux_path = args.session + '.codehash'
            if os.path.exists(aux_path):
                try:
                    with open(aux_path, 'r', encoding='utf-8') as f:
                        phone_code_hash = f.read().strip() or None
                except Exception:
                    phone_code_hash = None
            try:
                if phone_code_hash:
                    client.sign_in(phone=args.phone, code=args.code, phone_code_hash=phone_code_hash)
                else:
                    client.sign_in(phone=args.phone, code=args.code)
            except SessionPasswordNeededError:
                if not args.password:
                    print("ERR: password required", file=sys.stderr)
                    sys.exit(3)
                client.sign_in(password=args.password)
            print("OK: signed in")
        finally:
            client.disconnect()
            try:
                if os.path.exists(aux_path):
                    os.remove(aux_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()
