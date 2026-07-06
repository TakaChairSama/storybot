"""Discord content fetcher using a user token (self-bot).

Supports:
  • Regular thread channel:  https://discord.com/channels/{guild}/{channel}
  • Forum post (thread):     https://discord.com/channels/{guild}/{channel}/{thread_id}
  • Message permalink:       https://discord.com/channels/{guild}/{channel}/{message_id}

The user supplies their Discord user token (available in DevTools → Application
→ Local Storage → https://discord.com → key "token").

NOTE: Discord's Terms of Service prohibit automated self-bot usage.
This tool is for personal archival use only.
"""
import re
import time
import requests

DISCORD_API = "https://discord.com/api/v10"
MAX_MESSAGES = 1000  # safety cap per channel/thread


class DiscordClient:
    def __init__(self, token: str):
        self.token = token.strip().strip('"')
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "X-Super-Properties": "",
        })

    # ── URL parsing ────────────────────────────────────────────────────────────

    @staticmethod
    def parse_url(url: str) -> dict:
        """
        Parse a Discord channel/thread URL.
        Returns dict with guild_id, channel_id, and optionally thread_id.
        """
        url = url.strip()
        # https://discord.com/channels/{guild}/{channel}/{optional_thread_or_message}
        m = re.match(
            r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/"
            r"(\d+)/(\d+)(?:/(\d+))?",
            url,
        )
        if not m:
            raise ValueError(f"Cannot parse Discord URL: {url}")
        return {
            "guild_id": m.group(1),
            "channel_id": m.group(2),
            "extra_id": m.group(3),  # may be thread_id or message_id
        }

    # ── Low-level helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, params=None):
        resp = self.session.get(f"{DISCORD_API}{path}", params=params, timeout=15)
        if resp.status_code == 401:
            raise PermissionError(
                "Discord authentication failed. Please check your user token in Settings."
            )
        if resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 1)
            time.sleep(retry_after + 0.1)
            return self._get(path, params)
        resp.raise_for_status()
        return resp.json()

    def _fetch_all_messages(self, channel_id: str) -> list:
        """Fetch all messages from a channel/thread (paginated)."""
        messages = []
        last_id = None
        while len(messages) < MAX_MESSAGES:
            params = {"limit": 100}
            if last_id:
                params["before"] = last_id
            batch = self._get(f"/channels/{channel_id}/messages", params=params)
            if not batch:
                break
            messages.extend(batch)
            if len(batch) < 100:
                break
            last_id = batch[-1]["id"]
            time.sleep(0.3)  # be gentle
        # Discord returns newest-first; reverse to chronological order
        messages.reverse()
        return messages

    # ── Channel / thread info ──────────────────────────────────────────────────

    def _get_channel(self, channel_id: str) -> dict:
        return self._get(f"/channels/{channel_id}")

    def is_authenticated(self) -> bool:
        try:
            self._get("/users/@me")
            return True
        except Exception:
            return False

    # ── Main fetch ─────────────────────────────────────────────────────────────

    def fetch_thread(self, url: str) -> dict:
        """
        Fetch all messages from a Discord thread or channel.
        Returns:
          {
            "title": str,
            "channel_type": str,
            "messages": [{"author": str, "content": str, "timestamp": str}, ...],
            "message_count": int,
          }
        """
        parsed = self.parse_url(url)
        channel_id = parsed["channel_id"]
        extra_id = parsed["extra_id"]

        # Determine what we're looking at
        channel_info = self._get_channel(channel_id)
        channel_type = channel_info.get("type", 0)

        # Types: 0=text, 11=public thread, 12=private thread, 15=forum channel
        # If extra_id is provided for a forum channel, it's the thread (post)
        fetch_id = channel_id

        if extra_id:
            # Try treating extra_id as a thread/channel
            try:
                thread_info = self._get_channel(extra_id)
                fetch_id = extra_id
                channel_info = thread_info
                channel_type = thread_info.get("type", 0)
            except Exception:
                # extra_id might be a message ID; fall back to channel
                pass
        elif channel_type == 15:
            # Forum channel without a specific thread — list active threads
            return self._fetch_forum_overview(channel_id, channel_info)

        title = channel_info.get("name") or channel_info.get("topic") or f"Channel {fetch_id}"
        messages = self._fetch_all_messages(fetch_id)
        formatted = [self._format_message(m) for m in messages]

        return {
            "title": title,
            "channel_type": self._channel_type_name(channel_type),
            "messages": formatted,
            "message_count": len(formatted),
        }

    def _fetch_forum_overview(self, channel_id: str, channel_info: dict) -> dict:
        """Fetch active (and recently archived) forum threads in a forum channel."""
        threads = []
        try:
            active = self._get(f"/channels/{channel_id}/threads/active")
            threads.extend(active.get("threads", []))
        except Exception:
            pass
        try:
            archived = self._get(f"/channels/{channel_id}/threads/archived/public")
            threads.extend(archived.get("threads", []))
        except Exception:
            pass

        all_messages = []
        for t in threads:
            try:
                msgs = self._fetch_all_messages(t["id"])
                for m in msgs:
                    m["_thread_name"] = t.get("name", "")
                all_messages.extend(msgs)
                time.sleep(0.2)
            except Exception:
                pass

        all_messages.sort(key=lambda m: m.get("timestamp", ""))
        formatted = [self._format_message(m) for m in all_messages]

        return {
            "title": channel_info.get("name", f"Forum {channel_id}"),
            "channel_type": "forum",
            "messages": formatted,
            "message_count": len(formatted),
        }

    @staticmethod
    def _format_message(msg: dict) -> dict:
        author = msg.get("author") or {}
        name = author.get("global_name") or author.get("username") or "Unknown"
        content = msg.get("content", "")
        # Strip mentions/embeds but keep text
        timestamp = msg.get("timestamp", "")
        thread_tag = f"[{msg['_thread_name']}] " if msg.get("_thread_name") else ""
        return {
            "author": name,
            "content": f"{thread_tag}{content}",
            "timestamp": timestamp,
        }

    @staticmethod
    def _channel_type_name(t: int) -> str:
        return {0: "text", 11: "thread", 12: "private_thread", 15: "forum"}.get(t, "unknown")

    @staticmethod
    def format_as_text(thread_data: dict) -> str:
        """Format fetched thread data as plain text."""
        lines = []
        lines.append(f"Title: {thread_data.get('title', 'Untitled')}")
        lines.append(f"Type: {thread_data.get('channel_type', 'unknown')}")
        lines.append(f"Messages: {thread_data.get('message_count', 0)}")
        lines.append("")
        for msg in thread_data.get("messages", []):
            ts = msg.get("timestamp", "")[:19].replace("T", " ")
            lines.append(f"[{ts}] {msg['author']}:")
            lines.append(msg["content"])
            lines.append("")
        return "\n".join(lines)
