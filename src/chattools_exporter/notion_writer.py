import time
import requests

NOTION_VERSION = "2022-06-28"


class NotionError(Exception):
    pass


class NotionClient:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })

    def _request(self, method, url, **kwargs):
        for attempt in range(5):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 429:
                # Rate limited
                wait = int(resp.headers.get("Retry-After", "1"))
                time.sleep(max(1, wait))
                continue
            if 200 <= resp.status_code < 300:
                if resp.content:
                    return resp.json()
                return None
            # transient 5xx
            if 500 <= resp.status_code < 600 and attempt < 4:
                time.sleep(1 + attempt)
                continue
            raise NotionError(f"Notion API error {resp.status_code}: {resp.text}")

    def get_database(self, database_id: str):
        return self._request("GET", f"https://api.notion.com/v1/databases/{database_id}")

    def get_page(self, page_id: str):
        return self._request("GET", f"https://api.notion.com/v1/pages/{page_id}")

    def search(self, query: str, filter_object: str | None = None):
        payload = {"query": query}
        if filter_object:
            payload["filter"] = {"value": filter_object, "property": "object"}
        return self._request("POST", "https://api.notion.com/v1/search", json=payload)

    def append_children(self, page_id: str, children: list[dict]):
        # Append children blocks to a page (page is also a block)
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        payload = {"children": children}
        return self._request("PATCH", url, json=payload)

    def find_title_property_name(self, database: dict) -> str:
        props = database.get("properties", {})
        for name, meta in props.items():
            if meta.get("type") == "title":
                return name
        # Fallback common name
        return "Name"

    def create_page_in_database(self, database_id: str, title_prop: str, title: str, children: list[dict]):
        payload = {
            "parent": {"database_id": database_id},
            "properties": {
                title_prop: {"title": [{"type": "text", "text": {"content": title[:2000]}}]}
            },
            "children": children,
        }
        return self._request("POST", "https://api.notion.com/v1/pages", json=payload)

    def create_child_page(self, parent_page_id: str, title: str, children: list[dict]):
        payload = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": title[:2000]}}]}
            },
            "children": children,
        }
        return self._request("POST", "https://api.notion.com/v1/pages", json=payload)


def make_blocks_from_row(row: dict) -> list[dict]:
    blocks = []
    def add_paragraph(text: str):
        if not text:
            return
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            }
        })

    title_line = f"{row.get('chat_title', '')} • {row.get('id', '')} • {row.get('date', '')}"
    add_paragraph(title_line)
    add_paragraph(f"Sender: {row.get('sender_display') or row.get('sender_username') or row.get('sender_id')}")
    if row.get("reply_to_id"):
        add_paragraph(f"Reply to: {row['reply_to_id']}")
    if row.get("media"):
        add_paragraph(f"Media: {row.get('media_type')} {row.get('media_file_name') or ''}")
        if row.get("media_path"):
            add_paragraph(f"Media path: {row['media_path']}")
    text = row.get("text") or ""
    if text:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            }
        })
    return blocks


def test_connection(api_key: str, dest_type: str, parent_id: str) -> str:
    client = NotionClient(api_key)
    if dest_type.lower().startswith("data"):
        db = client.get_database(parent_id)
        title = db.get("title", [])
        title_text = "".join([t.get("plain_text", "") for t in title])
        return f"Database OK: {title_text or parent_id}"
    else:
        pg = client.get_page(parent_id)
        return f"Page OK: {pg.get('id', parent_id)}"


class NotionSink:
    def __init__(self, api_key: str, dest_type: str, parent_id: str, mode: str = "per_message", on_progress=None):
        self.client = NotionClient(api_key)
        self.dest_type = dest_type
        self.parent_id = parent_id
        self.mode = mode  # 'per_message' or 'group_by_day'
        self.on_progress = on_progress
        self.title_prop = None
        self.group = {}  # date -> list of blocks
        if self.dest_type.lower().startswith("data"):
            db = self.client.get_database(self.parent_id)
            self.title_prop = self.client.find_title_property_name(db)

    def __call__(self, row, _message, _client):
        if self.mode == "group_by_day" and self.dest_type.lower().startswith("page"):
            # Group by date (YYYY-MM-DD) from row['date']
            date_str = (row.get('date') or '')[:10]
            blocks = make_blocks_from_row(row)
            # add a divider between messages
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            self.group.setdefault(date_str, []).extend(blocks)
            if self.on_progress:
                self.on_progress(f"Queued for {date_str}: message {row.get('id')}")
            return

        # Default behavior: create page per message
        title = f"{row.get('chat_title', '')} • {row.get('id', '')} • {row.get('date', '')}"
        children = make_blocks_from_row(row)
        if self.dest_type.lower().startswith("data"):
            self.client.create_page_in_database(self.parent_id, self.title_prop, title, children)
        else:
            self.client.create_child_page(self.parent_id, title, children)
        if self.on_progress:
            self.on_progress(f"Notion: wrote message {row.get('id')}")

    def finalize(self, chat_title: str | None = None):
        if self.mode != "group_by_day" or not self.group:
            return
        # Create one page per day under the parent page, chunking children blocks
        for date_str, blocks in self.group.items():
            title = f"{chat_title or ''} • {date_str}"
            # Create an empty page first
            pg = self.client.create_child_page(self.parent_id, title, children=[])
            page_id = pg.get("id")
            # Chunk blocks (Notion limit ~100 per call)
            max_chunk = 80
            for i in range(0, len(blocks), max_chunk):
                chunk = blocks[i:i+max_chunk]
                self.client.append_children(page_id, chunk)
            if self.on_progress:
                self.on_progress(f"Notion: wrote day page {date_str} with {len(blocks)} blocks")


def notion_sink(api_key: str, dest_type: str, parent_id: str, mode: str = "per_message", on_progress=None):
    return NotionSink(api_key, dest_type, parent_id, mode=mode, on_progress=on_progress)

