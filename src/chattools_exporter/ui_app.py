import os
import json
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .export_telegram import export_messages
from .export_slack import export_slack_messages, test_slack_token
from .notion_writer import notion_sink, test_connection as notion_test

try:
    from telethon.sync import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except Exception:
    TelegramClient = None
    SessionPasswordNeededError = Exception


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DEFAULT_SESSION = os.path.join(APP_DIR, "tg_export.session")


def load_config():
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
        "slack": {
            "token": ""
        },
        "notion": {
            "destinations": []  # list of {name, api_key, type, parent_id, parent_title}
        },
        "defaults": {
            "reverse": True,
            "resume": True,
            "format": "jsonl",
            "only": "all",  # all|media|text
            "last_output_folder": APP_DIR,
            "filename": "messages.jsonl",
            "destination": "Folder (local)",
            "notion_mode": "per_message",
        }
    }


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chat Exporter")
        self.geometry("760x560")

        self.cfg = load_config()
        self._build_ui()

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        self.extract_frame = ttk.Frame(nb)
        self.settings_frame = ttk.Frame(nb)
        self.tg_help_frame = ttk.Frame(nb)
        self.slack_help_frame = ttk.Frame(nb)
        nb.add(self.extract_frame, text="Extract")
        nb.add(self.settings_frame, text="Settings")
        nb.add(self.tg_help_frame, text="Telegram Help")
        nb.add(self.slack_help_frame, text="Slack Help")

        self._build_extract_page()
        self._build_settings_page()
        self._build_help_pages()

    def _build_extract_page(self):
        p = self.extract_frame

        # App selector
        row = 0
        ttk.Label(p, text="Chat Application:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.app_var = tk.StringVar(value=self.cfg.get("app", "Telegram"))
        app_opts = ["Telegram", "Slack (coming soon)", "Teams (coming soon)"]
        self.app_combo = ttk.Combobox(p, textvariable=self.app_var, values=app_opts, state="readonly")
        self.app_combo.grid(row=row, column=1, sticky="we", padx=8, pady=6, columnspan=3)
        self.app_combo.bind("<<ComboboxSelected>>", self._on_app_change)

        # Chat identifier
        row += 1
        self.chat_label = ttk.Label(p, text="Chat / Channel:")
        self.chat_label.grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.chat_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.chat_var).grid(row=row, column=1, columnspan=2, sticky="we", padx=8, pady=6)
        self.slack_pick_btn = ttk.Button(p, text="Pick Channel...", command=self._slack_pick_channel)
        self.slack_pick_btn.grid(row=row, column=3, sticky="we", padx=8, pady=6)

        # Dates
        row += 1
        ttk.Label(p, text="Min Date (YYYY-MM-DD):").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.min_date_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.min_date_var, width=16).grid(row=row, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(p, text="Max Date (YYYY-MM-DD):").grid(row=row, column=2, sticky="w", padx=8, pady=6)
        self.max_date_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.max_date_var, width=16).grid(row=row, column=3, sticky="w", padx=8, pady=6)

        # Content type
        row += 1
        self.only_var = tk.StringVar(value=self.cfg["defaults"].get("only", "all"))
        ttk.Label(p, text="Content:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ttk.Radiobutton(p, text="All", variable=self.only_var, value="all").grid(row=row, column=1, sticky="w", padx=8)
        ttk.Radiobutton(p, text="Only media", variable=self.only_var, value="media").grid(row=row, column=2, sticky="w", padx=8)
        ttk.Radiobutton(p, text="Only text", variable=self.only_var, value="text").grid(row=row, column=3, sticky="w", padx=8)

        # Format and limit
        row += 1
        ttk.Label(p, text="Format:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.format_var = tk.StringVar(value=self.cfg["defaults"].get("format", "jsonl"))
        ttk.Combobox(p, textvariable=self.format_var, state="readonly", values=["jsonl", "csv"]).grid(row=row, column=1, sticky="we", padx=8, pady=6)
        ttk.Label(p, text="Limit:").grid(row=row, column=2, sticky="w", padx=8, pady=6)
        self.limit_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.limit_var, width=12).grid(row=row, column=3, sticky="w", padx=8, pady=6)

        # Filters: users, keywords
        row += 1
        ttk.Label(p, text="Users (comma, ids/usernames):").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.users_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.users_var).grid(row=row, column=1, columnspan=3, sticky="we", padx=8, pady=6)

        row += 1
        ttk.Label(p, text="Keywords (comma):").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.keywords_var = tk.StringVar()
        ttk.Entry(p, textvariable=self.keywords_var).grid(row=row, column=1, columnspan=3, sticky="we", padx=8, pady=6)

        # Options
        row += 1
        self.reverse_var = tk.BooleanVar(value=self.cfg["defaults"].get("reverse", True))
        ttk.Checkbutton(p, text="Oldest → newest", variable=self.reverse_var).grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.resume_var = tk.BooleanVar(value=self.cfg["defaults"].get("resume", True))
        ttk.Checkbutton(p, text="Resume (JSONL)", variable=self.resume_var).grid(row=row, column=1, sticky="w", padx=8, pady=6)
        self.media_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(p, text="Download media", variable=self.media_var).grid(row=row, column=2, sticky="w", padx=8, pady=6)

        # Destination
        row += 1
        ttk.Label(p, text="Destination:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.dest_var = tk.StringVar(value=self.cfg["defaults"].get("destination", "Folder (local)"))
        self.dest_combo = ttk.Combobox(p, textvariable=self.dest_var, state="readonly")
        self.dest_combo.grid(row=row, column=1, sticky="we", padx=8, pady=6)
        self.dest_combo.bind("<<ComboboxSelected>>", self._on_dest_change)

        # Output folder + filename
        row += 1
        ttk.Label(p, text="Output folder:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.out_folder_var = tk.StringVar(value=self.cfg["defaults"].get("last_output_folder", APP_DIR))
        ttk.Entry(p, textvariable=self.out_folder_var).grid(row=row, column=1, sticky="we", padx=8, pady=6)
        ttk.Button(p, text="Choose...", command=self.choose_folder).grid(row=row, column=2, padx=8, pady=6)

        row += 1
        ttk.Label(p, text="Filename:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.filename_var = tk.StringVar(value=self.cfg["defaults"].get("filename", "messages.jsonl"))
        ttk.Entry(p, textvariable=self.filename_var).grid(row=row, column=1, columnspan=2, sticky="we", padx=8, pady=6)

        # Notion write mode (visible when Notion selected)
        row += 1
        ttk.Label(p, text="Notion write mode:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.notion_mode_var = tk.StringVar(value=self.cfg["defaults"].get("notion_mode", "per_message"))
        self.notion_mode_combo = ttk.Combobox(p, textvariable=self.notion_mode_var, state="readonly", values=["per_message", "group_by_day"])
        self.notion_mode_combo.grid(row=row, column=1, sticky="we", padx=8, pady=6)

        # Extract button
        row += 1
        self.extract_btn = ttk.Button(p, text="Extract", command=self.start_extract)
        self.extract_btn.grid(row=row, column=0, padx=8, pady=10, sticky="w")

        # Progress + log
        self.progress = ttk.Progressbar(p, mode="indeterminate")
        self.progress.grid(row=row, column=1, columnspan=2, padx=8, pady=10, sticky="we")

        row += 1
        self.log = tk.Text(p, height=14)
        self.log.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=8, pady=6)
        p.grid_rowconfigure(row, weight=1)
        for c in range(4):
            p.grid_columnconfigure(c, weight=1)

        # Initial state
        self._refresh_destinations()
        self._on_app_change()
        self._on_dest_change()

    def _build_settings_page(self):
        p = self.settings_frame
        row = 0
        ttk.Label(p, text="Telegram Settings").grid(row=row, column=0, sticky="w", padx=8, pady=8)

        row += 1
        ttk.Label(p, text="API ID:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.api_id_var = tk.StringVar(value=self.cfg["telegram"].get("api_id", ""))
        ttk.Entry(p, textvariable=self.api_id_var).grid(row=row, column=1, sticky="we", padx=8, pady=6)

        row += 1
        ttk.Label(p, text="API Hash:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.api_hash_var = tk.StringVar(value=self.cfg["telegram"].get("api_hash", ""))
        ttk.Entry(p, textvariable=self.api_hash_var).grid(row=row, column=1, sticky="we", padx=8, pady=6)

        row += 1
        ttk.Label(p, text="Phone Number:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.phone_var = tk.StringVar(value=self.cfg["telegram"].get("phone", ""))
        ttk.Entry(p, textvariable=self.phone_var).grid(row=row, column=1, sticky="we", padx=8, pady=6)

        row += 1
        ttk.Label(p, text="Session File:").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.session_var = tk.StringVar(value=self.cfg["telegram"].get("session", DEFAULT_SESSION))
        ttk.Entry(p, textvariable=self.session_var).grid(row=row, column=1, sticky="we", padx=8, pady=6)

        row += 1
        ttk.Button(p, text="Save Settings", command=self.save_settings).grid(row=row, column=0, padx=8, pady=10, sticky="w")
        ttk.Button(p, text="Test Login", command=self.test_login).grid(row=row, column=1, padx=8, pady=10, sticky="w")
        ttk.Button(p, text="Log out / Clear session", command=self.clear_session).grid(row=row, column=2, padx=8, pady=10, sticky="w")

        for c in range(3):
            p.grid_columnconfigure(c, weight=1)

        # Slack settings
        row += 1
        sep1 = ttk.Separator(p)
        sep1.grid(row=row, column=0, columnspan=3, sticky="we", pady=10)

        row += 1
        ttk.Label(p, text="Slack Settings").grid(row=row, column=0, sticky="w", padx=8, pady=8)

        row += 1
        ttk.Label(p, text="Token (SLACK_TOKEN):").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        self.slack_token_var = tk.StringVar(value=self.cfg["slack"].get("token", ""))
        ttk.Entry(p, textvariable=self.slack_token_var, show='*').grid(row=row, column=1, sticky="we", padx=8, pady=6)
        ttk.Button(p, text="Test Slack", command=self.test_slack).grid(row=row, column=2, padx=8, pady=6, sticky="w")

        # Notion destinations
        row += 1
        sep = ttk.Separator(p)
        sep.grid(row=row, column=0, columnspan=3, sticky="we", pady=10)

        row += 1
        ttk.Label(p, text="Notion Destinations").grid(row=row, column=0, sticky="w", padx=8, pady=8)

        row += 1
        left = ttk.Frame(p)
        left.grid(row=row, column=0, sticky="nsew", padx=8)
        right = ttk.Frame(p)
        right.grid(row=row, column=1, columnspan=2, sticky="nsew", padx=8)
        p.grid_rowconfigure(row, weight=1)
        p.grid_columnconfigure(0, weight=1)
        p.grid_columnconfigure(1, weight=2)

        ttk.Label(left, text="Saved Destinations:").pack(anchor="w")
        self.notion_list = tk.Listbox(left, height=8)
        self.notion_list.pack(fill=tk.BOTH, expand=True)
        self.notion_list.bind("<<ListboxSelect>>", self._on_notion_select)

        ttk.Button(left, text="Remove", command=self._notion_remove).pack(pady=6)

        # Right side form
        rrow = 0
        ttk.Label(right, text="Output Source Name:").grid(row=rrow, column=0, sticky="w")
        self.notion_name = tk.StringVar()
        ttk.Entry(right, textvariable=self.notion_name).grid(row=rrow, column=1, sticky="we", padx=8, pady=4)

        rrow += 1
        ttk.Label(right, text="API Key (Integration Secret):").grid(row=rrow, column=0, sticky="w")
        self.notion_key = tk.StringVar()
        ttk.Entry(right, textvariable=self.notion_key, show='*').grid(row=rrow, column=1, sticky="we", padx=8, pady=4)

        rrow += 1
        ttk.Label(right, text="Destination Type:").grid(row=rrow, column=0, sticky="w")
        self.notion_type = tk.StringVar(value="Database")
        ttk.Combobox(right, textvariable=self.notion_type, state="readonly", values=["Database", "Page"]).grid(row=rrow, column=1, sticky="we", padx=8, pady=4)

        rrow += 1
        ttk.Label(right, text="Parent ID (Database/Page ID):").grid(row=rrow, column=0, sticky="w")
        self.notion_parent = tk.StringVar()
        ttk.Entry(right, textvariable=self.notion_parent).grid(row=rrow, column=1, sticky="we", padx=8, pady=4)

        rrow += 1
        btns = ttk.Frame(right)
        btns.grid(row=rrow, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(btns, text="Add/Update", command=self._notion_add_update).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Test Connection", command=self._notion_test).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Pick Parent...", command=self._notion_pick_parent).pack(side=tk.LEFT, padx=4)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.out_folder_var.set(path)

    def append_log(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def _on_app_change(self, *_):
        app = self.app_var.get()
        enabled = app.startswith("Telegram") or app.startswith("Slack")
        for w in [
            self.extract_btn, self.app_combo
        ]:
            w.configure(state="normal")
        # Enable/disable Telegram-specific inputs
        state = "normal" if enabled else "disabled"
        for w in self.extract_frame.winfo_children():
            # Leave app selector and log always enabled
            if isinstance(w, ttk.Combobox) and w is self.app_combo:
                continue
            if w is self.log:
                continue
            try:
                w.configure(state=state)
            except tk.TclError:
                pass
        # Re-enable app selector regardless
        self.app_combo.configure(state="readonly")
        self.log.configure(state="normal")
        # Adjust label for Slack
        if app.startswith("Slack"):
            self.chat_label.configure(text="Channel (#name or ID):")
            try:
                self.slack_pick_btn.configure(state="normal")
            except Exception:
                pass
        else:
            self.chat_label.configure(text="Chat / Channel:")
            try:
                self.slack_pick_btn.configure(state="disabled")
            except Exception:
                pass
        if not enabled:
            self.append_log("Selected app not implemented yet. Choose Telegram or Slack.")

    def _on_dest_change(self, *_):
        dest = self.dest_var.get()
        is_folder = dest.startswith("Folder")
        # Ensure Extract is enabled for both Folder and Notion
        self.extract_btn.configure(state="normal")
        # Disable media download for Notion (no file output path referenced)
        try:
            self.media_var.set(self.media_var.get() if is_folder else False)
        except Exception:
            pass
        if not is_folder:
            self.append_log("Destination: Notion selected. Folder/filename fields will be ignored.")
        # Toggle Notion mode visibility
        try:
            state = "disabled" if is_folder else "readonly"
            self.notion_mode_combo.configure(state=state)
        except Exception:
            pass

    def save_settings(self):
        self.cfg["app"] = self.app_var.get()
        self.cfg["telegram"]["api_id"] = self.api_id_var.get().strip()
        self.cfg["telegram"]["api_hash"] = self.api_hash_var.get().strip()
        self.cfg["telegram"]["phone"] = self.phone_var.get().strip()
        self.cfg["telegram"]["session"] = self.session_var.get().strip() or DEFAULT_SESSION
        self.cfg["defaults"]["reverse"] = bool(self.reverse_var.get())
        self.cfg["defaults"]["resume"] = bool(self.resume_var.get())
        self.cfg["defaults"]["format"] = self.format_var.get()
        self.cfg["defaults"]["only"] = self.only_var.get()
        self.cfg["defaults"]["last_output_folder"] = self.out_folder_var.get()
        self.cfg["defaults"]["filename"] = self.filename_var.get()
        self.cfg["defaults"]["destination"] = self.dest_var.get()
        self.cfg["defaults"]["notion_mode"] = self.notion_mode_var.get()
        self.cfg.setdefault("slack", {})["token"] = self.slack_token_var.get().strip()
        save_config(self.cfg)
        messagebox.showinfo("Saved", "Settings saved.")

    def clear_session(self):
        path = self.session_var.get()
        if os.path.exists(path):
            os.remove(path)
            messagebox.showinfo("Session", "Session cleared.")
        else:
            messagebox.showinfo("Session", "No session file found.")

    def test_login(self):
        if TelegramClient is None:
            messagebox.showerror("Error", "Telethon not installed. Run run_ui.ps1 once to install dependencies.")
            return
        try:
            api_id = int(self.api_id_var.get())
        except ValueError:
            messagebox.showerror("Error", "API ID must be an integer.")
            return
        api_hash = self.api_hash_var.get().strip()
        phone = self.phone_var.get().strip()
        session = self.session_var.get().strip() or DEFAULT_SESSION
        if not (api_id and api_hash and phone):
            messagebox.showerror("Error", "Please fill API ID, API Hash, and Phone Number.")
            return
        def do_login():
            try:
                with TelegramClient(session, api_id, api_hash) as client:
                    if not client.is_user_authorized():
                        client.send_code_request(phone)
                        code = simpledialog.askstring("Login", "Enter the login code sent to Telegram:")
                        if code is None:
                            self.append_log("Login cancelled.")
                            return
                        try:
                            client.sign_in(phone=phone, code=code)
                        except SessionPasswordNeededError:
                            pw = simpledialog.askstring("2FA", "Enter your Telegram password:", show='*')
                            if pw is None:
                                self.append_log("2FA cancelled.")
                                return
                            client.sign_in(password=pw)
                    me = client.get_me()
                    self.append_log(f"Logged in as: {getattr(me, 'username', None) or me.first_name}")
                    messagebox.showinfo("Login", "Login successful.")
            except Exception as e:
                messagebox.showerror("Login failed", str(e))

        threading.Thread(target=do_login, daemon=True).start()

    def start_extract(self):
        # Validate
        if not self.chat_var.get().strip():
            messagebox.showerror("Error", "Please enter a chat/channel.")
            return
        try:
            api_id = int(self.api_id_var.get())
        except ValueError:
            messagebox.showerror("Error", "API ID must be an integer.")
            return
        api_hash = self.api_hash_var.get().strip()
        session = self.session_var.get().strip() or DEFAULT_SESSION
        if not (api_id and api_hash):
            messagebox.showerror("Error", "Please enter API ID and API Hash in Settings.")
            return

        app = self.app_var.get()
        dest = self.dest_var.get()
        is_folder = dest.startswith("Folder")

        if is_folder:
            out_folder = self.out_folder_var.get().strip()
            if not out_folder:
                messagebox.showerror("Error", "Please choose an output folder.")
                return
            if not os.path.isdir(out_folder):
                try:
                    os.makedirs(out_folder, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("Error", f"Cannot create folder: {e}")
                    return

            filename = self.filename_var.get().strip()
            if not filename:
                messagebox.showerror("Error", "Please enter a filename.")
                return

            fmt = self.format_var.get()
            if not (filename.lower().endswith(".jsonl") or filename.lower().endswith(".csv")):
                # Adjust extension based on selected format
                filename += f".{fmt}"

            out_path = os.path.join(out_folder, filename)
            media_dir = os.path.join(out_folder, "media") if self.media_var.get() else None
        else:
            out_path = None
            fmt = None
            media_dir = None

        only_media = self.only_var.get() == "media"
        only_text = self.only_var.get() == "text"

        keywords = [k.strip() for k in self.keywords_var.get().split(',')] if self.keywords_var.get().strip() else []
        users = [u.strip().lstrip('@') for u in self.users_var.get().split(',')] if self.users_var.get().strip() else []

        min_date = self.min_date_var.get().strip() or None
        max_date = self.max_date_var.get().strip() or None
        try:
            if min_date:
                datetime.strptime(min_date, "%Y-%m-%d")
            if max_date:
                datetime.strptime(max_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Dates must be in YYYY-MM-DD format.")
            return

        limit = None
        if self.limit_var.get().strip():
            try:
                limit = int(self.limit_var.get().strip())
            except ValueError:
                messagebox.showerror("Error", "Limit must be an integer.")
                return

        self.extract_btn.configure(state="disabled")
        self.progress.start(12)
        self.append_log("Starting export...")

        def run_export():
            try:
                sink = None
                if not is_folder:
                    # Notion destination selected
                    # Parse chosen Notion entry
                    sel = dest.removeprefix("Notion: ").strip()
                    # Find matching config
                    ndests = self.cfg.get("notion", {}).get("destinations", [])
                    match = None
                    for d in ndests:
                        label = f"{d.get('name')} ({d.get('type')})"
                        if label == sel:
                            match = d
                            break
                    if not match:
                        # Try by name only
                        for d in ndests:
                            if d.get('name') == sel:
                                match = d
                                break
                    if not match:
                        raise Exception("Selected Notion destination not found in settings.")
                    sink = notion_sink(
                        match.get('api_key'),
                        match.get('type'),
                        match.get('parent_id'),
                        mode=self.notion_mode_var.get(),
                        on_progress=self.append_log,
                    )

                if app.startswith("Telegram"):
                    count = export_messages(
                        api_id=api_id,
                        api_hash=api_hash,
                        session=session,
                        chat=self.chat_var.get().strip(),
                        out_path=out_path or "",
                        out_fmt=fmt or "jsonl",
                        reverse=bool(self.reverse_var.get()),
                        resume=bool(self.resume_var.get()),
                        limit=limit,
                        media_dir=media_dir,
                        min_date=min_date,
                        max_date=max_date,
                        only_media=only_media,
                        only_text=only_text,
                        keywords=keywords,
                        users=users,
                        on_progress=lambda msg: self.append_log(msg),
                        sink=sink,
                    )
                elif app.startswith("Slack"):
                    token = self.slack_token_var.get().strip()
                    if not token:
                        raise Exception("Enter Slack token in Settings.")
                    count = export_slack_messages(
                        token=token,
                        channel=self.chat_var.get().strip(),
                        out_path=out_path or "",
                        out_fmt=fmt or "jsonl",
                        reverse=bool(self.reverse_var.get()),
                        resume=bool(self.resume_var.get()),
                        limit=limit,
                        media_dir=media_dir,
                        min_date=min_date,
                        max_date=max_date,
                        only_media=only_media,
                        only_text=only_text,
                        keywords=keywords,
                        users=users,
                        on_progress=lambda msg: self.append_log(msg),
                        sink=sink,
                    )
                else:
                    raise Exception("Selected app not implemented.")
                # Finalize sinks that support it (e.g., Notion group_by_day)
                try:
                    if sink and hasattr(sink, 'finalize'):
                        sink.finalize(chat_title=self.chat_var.get().strip())
                except Exception as e:
                    self.append_log(f"Finalize error: {e}")
                self.append_log(f"Export complete. {count} messages.")
            except Exception as e:
                self.append_log(f"Error: {e}")
                messagebox.showerror("Export failed", str(e))
            finally:
                self.progress.stop()
                self.extract_btn.configure(state="normal")
                # Save defaults for next time
                self.save_settings()

        threading.Thread(target=run_export, daemon=True).start()

    def _refresh_destinations(self):
        # Build destination dropdown values
        values = ["Folder (local)"]
        ndests = self.cfg.get("notion", {}).get("destinations", [])
        for d in ndests:
            values.append(f"Notion: {d.get('name')} ({d.get('type')})")
        self.dest_combo.configure(values=values)
        # Ensure current value is valid
        if self.dest_var.get() not in values:
            self.dest_var.set("Folder (local)")
        # Refresh Notion listbox
        if hasattr(self, 'notion_list'):
            self.notion_list.delete(0, tk.END)
            for d in ndests:
                self.notion_list.insert(tk.END, f"{d.get('name')} ({d.get('type')})")

    def _on_notion_select(self, *_):
        sel = self.notion_list.curselection()
        if not sel:
            return
        idx = sel[0]
        d = self.cfg.get("notion", {}).get("destinations", [])[idx]
        self.notion_name.set(d.get('name', ''))
        self.notion_key.set(d.get('api_key', ''))
        self.notion_type.set(d.get('type', 'Database'))
        self.notion_parent.set(d.get('parent_id', ''))

    def _notion_remove(self):
        sel = self.notion_list.curselection()
        if not sel:
            return
        idx = sel[0]
        ndests = self.cfg.get("notion", {}).get("destinations", [])
        if 0 <= idx < len(ndests):
            ndests.pop(idx)
            save_config(self.cfg)
            self._refresh_destinations()

    def _notion_add_update(self):
        name = self.notion_name.get().strip()
        key = self.notion_key.get().strip()
        dtype = self.notion_type.get().strip()
        parent = self.notion_parent.get().strip()
        if not (name and key and dtype and parent):
            messagebox.showerror("Notion", "Please fill Name, API Key, Type, and Parent ID.")
            return
        ndests = self.cfg.setdefault("notion", {}).setdefault("destinations", [])
        # Update if name matches, else append
        for d in ndests:
            if d.get('name') == name:
                d.update({"api_key": key, "type": dtype, "parent_id": parent})
                break
        else:
            ndests.append({"name": name, "api_key": key, "type": dtype, "parent_id": parent})
        save_config(self.cfg)
        self._refresh_destinations()
        messagebox.showinfo("Notion", "Destination saved.")

    def _notion_test(self):
        key = self.notion_key.get().strip()
        dtype = self.notion_type.get().strip()
        parent = self.notion_parent.get().strip()
        if not (key and dtype and parent):
            messagebox.showerror("Notion", "Please fill API Key, Type, and Parent ID.")
            return
        try:
            msg = notion_test(key, dtype, parent)
            messagebox.showinfo("Notion", msg)
        except Exception as e:
            messagebox.showerror("Notion", str(e))

    def _notion_pick_parent(self):
        # Simple search dialog to pick a database or page
        key = self.notion_key.get().strip()
        if not key:
            messagebox.showerror("Notion", "Enter your Notion API Key first.")
            return
        import tkinter.simpledialog as sd
        query = sd.askstring("Notion", "Search pages/databases by title:")
        if query is None:
            return
        try:
            from .notion_writer import NotionClient
            client = NotionClient(key)
            res = client.search(query)
            items = []
            for r in res.get('results', []):
                obj = r.get('object')
                rid = r.get('id')
                title = ''
                if obj == 'database':
                    title = ''.join([t.get('plain_text','') for t in r.get('title', [])]) or '(untitled database)'
                    items.append((f"Database • {title}", 'Database', rid))
                elif obj == 'page':
                    # Try to get a name from properties
                    props = r.get('properties', {})
                    title_prop = None
                    for name, meta in props.items():
                        if meta.get('type') == 'title':
                            title_prop = name
                            break
                    if title_prop:
                        title_arr = props[title_prop].get('title', [])
                        title = ''.join([t.get('plain_text','') for t in title_arr]) or '(untitled page)'
                    else:
                        title = '(page)'
                    items.append((f"Page • {title}", 'Page', rid))
            if not items:
                messagebox.showinfo("Notion", "No results found.")
                return
            # Selection window
            win = tk.Toplevel(self)
            win.title("Pick Notion Parent")
            win.geometry("520x360")
            lb = tk.Listbox(win)
            lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            for label, _t, _id in items:
                lb.insert(tk.END, label)
            def on_choose():
                sel = lb.curselection()
                if not sel:
                    return
                i = sel[0]
                label, typ, rid = items[i]
                self.notion_type.set(typ)
                self.notion_parent.set(rid)
                win.destroy()
            ttk.Button(win, text="Choose", command=on_choose).pack(pady=6)
        except Exception as e:
            messagebox.showerror("Notion", str(e))

    def _slack_pick_channel(self):
        # Only for Slack app
        app = self.app_var.get()
        if not app.startswith("Slack"):
            return
        token = self.slack_token_var.get().strip()
        if not token:
            messagebox.showerror("Slack", "Enter your Slack token in Settings first.")
            return
        import tkinter.simpledialog as sd
        query = sd.askstring("Slack", "Search channels by name (leave blank to list):")
        try:
            from slack_sdk import WebClient
            client = WebClient(token=token)
            items = []
            cursor = None
            cap = 0
            q = (query or "").lower()
            while True and cap < 2000:  # hard cap to keep it snappy
                res = client.conversations_list(limit=200, cursor=cursor, types="public_channel,private_channel")
                for c in res.get('channels', []):
                    name = c.get('name') or ''
                    if not q or q in name.lower():
                        items.append((name, c.get('id')))
                        cap += 1
                cursor = res.get('response_metadata', {}).get('next_cursor') or None
                if not cursor or cap >= 500:
                    break
            if not items:
                messagebox.showinfo("Slack", "No channels found.")
                return
            # Show selection
            win = tk.Toplevel(self)
            win.title("Pick Slack Channel")
            win.geometry("520x360")
            lb = tk.Listbox(win)
            lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            for name, cid in items:
                lb.insert(tk.END, f"#{name}    ({cid})")
            def use_name():
                sel = lb.curselection()
                if not sel:
                    return
                i = sel[0]
                name, cid = items[i]
                self.chat_var.set(f"#{name}")
                win.destroy()
            def use_id():
                sel = lb.curselection()
                if not sel:
                    return
                i = sel[0]
                name, cid = items[i]
                self.chat_var.set(cid)
                win.destroy()
            bar = ttk.Frame(win)
            bar.pack(pady=6)
            ttk.Button(bar, text="Use #name", command=use_name).pack(side=tk.LEFT, padx=6)
            ttk.Button(bar, text="Use ID", command=use_id).pack(side=tk.LEFT, padx=6)
        except Exception as e:
            messagebox.showerror("Slack", str(e))

    def _build_help_pages(self):
        # Telegram help
        self._add_help_text(
            self.tg_help_frame,
            """
Telegram Setup
---------------

1) Create API credentials:
   - Visit https://my.telegram.org → API Development Tools.
   - Create an application to get your API ID and API Hash.

2) Log in once in Settings:
   - Open the Settings tab in this app.
   - Enter API ID, API Hash, and your phone number.
   - Click Test Login and enter the code sent to Telegram (and 2FA password if enabled).
   - A session file is created so you won't be prompted again.

3) Access to chats:
   - You must be a member of private groups/channels to read their history.
   - Public channels can be read without joining (if accessible), by using @username or link.

4) Chat identifiers:
   - Use @username, full link (https://t.me/...), or numeric ID (e.g., -1001234567890).

5) Limits and notes:
   - Bots cannot backfill history; use a user session.
   - Media downloads may be rate-limited; the app will retry.
   - JSONL format supports resume; CSV appends rows.
"""
        )

        # Slack help
        self._add_help_text(
            self.slack_help_frame,
            """
Slack Setup
-----------

1) Get a token:
   - Create a Slack app at https://api.slack.com/apps or use an existing one.
   - Add scopes: channels:read, groups:read, channels:history, groups:history.
   - For file downloads, also add files:read.
   - Install the app to your workspace to obtain a Bot token (xoxb-...).
   - Alternatively, use a user token if appropriate (mind workspace policies).

2) Access control:
   - To access private channels, the token/app must be a member of those channels.
   - Add the app to the channel (e.g., /invite @your-app) if needed.

3) Configure in this app:
   - Open Settings → Slack, paste your token, and click Test Slack.
   - On Extract, choose Slack, then enter a channel (#name or channel ID), or use Pick Channel.

4) Filters and output:
   - Date range, only media/text, keywords, and users work similarly to Telegram.
   - JSONL/CSV output supported; Notion export can be used as destination as well.

5) Notes:
   - Slack API returns newest→oldest; enable Reverse to write oldest→newest.
   - Very large exports may be slower and subject to rate limits.
"""
        )

    def _add_help_text(self, frame, content: str):
        # Simple read-only text with vertical scrollbar
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap="word")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=vsb.set)
        text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        text.insert("1.0", content.strip() + "\n")
        text.configure(state="disabled")

    def test_slack(self):
        token = self.slack_token_var.get().strip()
        if not token:
            messagebox.showerror("Slack", "Enter a Slack token.")
            return
        try:
            msg = test_slack_token(token)
            messagebox.showinfo("Slack", msg)
        except Exception as e:
            messagebox.showerror("Slack", str(e))


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
