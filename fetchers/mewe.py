"""MeWe API client — email/password login + content fetching.

MeWe uses a private REST API.  The auth flow:
  1. GET  homepage                  → grab CSRF token from cookies
  2. POST /api/v2/auth/login        → send email + password, get session cookie

Post URLs look like:
  https://mewe.com/p/{userId}/{postId}
  https://mewe.com/group/{groupId}/post/{postId}
"""
import re
import json
import requests
from bs4 import BeautifulSoup

MEWE_BASE = "https://mewe.com"
API_BASE = f"{MEWE_BASE}/api/v2"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": MEWE_BASE,
    "Referer": f"{MEWE_BASE}/",
}


class MeWeClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._challenge_token = None

    # ── Authentication ─────────────────────────────────────────────────────────

    def _fetch_csrf(self):
        """Hit the MeWe homepage to seed cookies including CSRF token."""
        resp = self.session.get(MEWE_BASE, timeout=15)
        resp.raise_for_status()
        # MeWe sets a _csrf cookie that must be forwarded as x-csrf-token header
        csrf = self.session.cookies.get("_csrf", "")
        if csrf:
            self.session.headers["x-csrf-token"] = csrf
        return csrf

    def login_with_password(self, email: str, password: str) -> dict:
        """
        Log in with email and password.
        Returns {success: bool, error?: str}.
        """
        self._fetch_csrf()
        payload = {"username": email, "password": password}
        resp = self.session.post(
            f"{API_BASE}/auth/login",
            json=payload,
            timeout=15,
        )
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200:
            # Refresh CSRF from updated cookies after login
            csrf = self.session.cookies.get("_csrf", "")
            if csrf:
                self.session.headers["x-csrf-token"] = csrf
            # Confirm the session is actually authenticated
            if not self.is_authenticated():
                return {"success": False, "error": "Login appeared to succeed but session check failed."}
            return {"success": True, "data": data}
        error_msg = data.get("message") or data.get("error") or f"HTTP {resp.status_code}"
        return {"success": False, "error": error_msg}

    def start_phone_login(self, phone: str) -> dict:
        """
        Send phone number to start SMS OTP flow.
        Returns the server response (includes challengeToken on success).
        """
        self._fetch_csrf()
        payload = {"phone": phone}
        resp = self.session.post(
            f"{API_BASE}/auth/phone",
            json=payload,
            timeout=15,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"error": resp.text}
        if resp.status_code in (200, 201):
            self._challenge_token = data.get("challengeToken", "")
        return {"status": resp.status_code, "data": data}

    def verify_otp(self, otp: str) -> dict:
        """
        Verify the SMS OTP code.  On success the session cookie is set.
        Returns {success: bool, error?: str}.
        """
        if not self._challenge_token:
            return {"success": False, "error": "No challenge token — call start_phone_login first."}

        payload = {"code": otp, "challengeToken": self._challenge_token}
        resp = self.session.post(
            f"{API_BASE}/auth/phone/verify",
            json=payload,
            timeout=15,
        )
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code == 200:
            self._challenge_token = None
            return {"success": True, "data": data}
        return {"success": False, "error": data.get("message", f"HTTP {resp.status_code}")}

    def load_session_cookies(self, cookies: dict):
        """Restore a previously saved cookie dict."""
        self.session.cookies.update(cookies)
        csrf = cookies.get("_csrf", "")
        if csrf:
            self.session.headers["x-csrf-token"] = csrf

    def get_session_cookies(self) -> dict:
        return dict(self.session.cookies)

    def is_authenticated(self) -> bool:
        """Quick check — tries to hit the /me endpoint."""
        try:
            resp = self.session.get(f"{API_BASE}/me", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    # ── Content fetching ───────────────────────────────────────────────────────

    @staticmethod
    def parse_post_url(url: str) -> dict:
        """
        Extract identifiers from a MeWe post URL.
        Supports:
          https://mewe.com/p/{userId}/{postId}
          https://mewe.com/group/{groupId}/post/{postId}
          https://mewe.com/{username}/{postId}   (profile post)
        Returns dict with keys: type, userId/groupId, postId
        """
        url = url.strip().rstrip("/")

        # Profile post: /p/{userId}/{postId}
        m = re.match(r"https?://mewe\.com/p/([^/]+)/([^/?#]+)", url)
        if m:
            return {"type": "profile_post", "userId": m.group(1), "postId": m.group(2)}

        # Group post: /group/{groupId}/post/{postId}  or  /group/{groupId}/{postId}
        m = re.match(r"https?://mewe\.com/group/([^/]+)(?:/post)?/([^/?#]+)", url)
        if m:
            return {"type": "group_post", "groupId": m.group(1), "postId": m.group(2)}

        # Fallback: /{anything}/{postId}
        m = re.match(r"https?://mewe\.com/([^/]+)/([^/?#]+)", url)
        if m:
            return {"type": "profile_post", "userId": m.group(1), "postId": m.group(2)}

        raise ValueError(f"Cannot parse MeWe URL: {url}")

    def _extract_text(self, obj) -> str:
        """Recursively pull text from a MeWe API response object."""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, list):
            return " ".join(self._extract_text(i) for i in obj)
        if isinstance(obj, dict):
            # Common text fields in MeWe posts
            parts = []
            for key in ("text", "body", "content", "value"):
                if key in obj:
                    parts.append(self._extract_text(obj[key]))
            return " ".join(p for p in parts if p)
        return ""

    def fetch_post(self, url: str) -> dict:
        """
        Fetch a MeWe post and all its comments.
        Returns:
          {
            "title": str,
            "author": str,
            "body": str,
            "comments": [{"author": str, "text": str}, ...],
            "raw": {...}   # raw API response
          }
        """
        parsed = self.parse_post_url(url)

        if parsed["type"] == "group_post":
            endpoint = (
                f"{API_BASE}/group/{parsed['groupId']}/post/{parsed['postId']}"
            )
        else:
            endpoint = (
                f"{API_BASE}/home/user/{parsed['userId']}/postsFeed/{parsed['postId']}"
            )

        resp = self.session.get(endpoint, timeout=20)
        if resp.status_code == 401:
            raise PermissionError("Not authenticated with MeWe. Please log in.")
        resp.raise_for_status()

        data = resp.json()
        post = data.get("post", data)  # some endpoints nest under "post"

        author = self._get_author(post)
        body = self._extract_text(post.get("text") or post.get("body") or "")

        # Fetch comments
        comments = self._fetch_comments(parsed, post)

        return {
            "title": post.get("title") or f"Post by {author}",
            "author": author,
            "body": body,
            "comments": comments,
            "raw": data,
        }

    def _get_author(self, obj: dict) -> str:
        if "postedBy" in obj:
            u = obj["postedBy"]
            return f"{u.get('firstName', '')} {u.get('lastName', '')}".strip()
        if "user" in obj:
            u = obj["user"]
            return f"{u.get('firstName', '')} {u.get('lastName', '')}".strip()
        return "Unknown"

    def _fetch_comments(self, parsed: dict, post: dict) -> list:
        comments = []
        # Comments may be embedded
        for comment in post.get("comments", []):
            comments.append({
                "author": self._get_author(comment),
                "text": self._extract_text(comment.get("text") or comment.get("body") or ""),
            })

        # If there are more, paginate via comments endpoint
        post_id = parsed.get("postId", "")
        if parsed["type"] == "group_post":
            base = f"{API_BASE}/group/{parsed['groupId']}/post/{post_id}/comments"
        else:
            base = f"{API_BASE}/home/user/{parsed['userId']}/post/{post_id}/comments"

        try:
            page_resp = self.session.get(base, timeout=15)
            if page_resp.status_code == 200:
                cdata = page_resp.json()
                for c in cdata.get("comments", []):
                    comments.append({
                        "author": self._get_author(c),
                        "text": self._extract_text(c.get("text") or c.get("body") or ""),
                    })
        except Exception:
            pass  # embedded comments are sufficient fallback

        return comments

    @staticmethod
    def format_as_text(post_data: dict) -> str:
        """Format fetched post data as plain text."""
        lines = []
        lines.append(f"Title: {post_data.get('title', 'Untitled')}")
        lines.append(f"Author: {post_data.get('author', 'Unknown')}")
        lines.append("")
        lines.append(post_data.get("body", ""))
        lines.append("")
        lines.append(f"── Comments ({len(post_data.get('comments', []))}) ──")
        for c in post_data.get("comments", []):
            lines.append(f"\n[{c['author']}]")
            lines.append(c["text"])
        return "\n".join(lines)
