"""StoryBot — main Flask application."""
import os
import json
import pathlib
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, request, jsonify, render_template, session as flask_session
from flask_cors import CORS

import database as db
from fetchers.mewe import MeWeClient
from fetchers.discord import DiscordClient
from ai import analyzer

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32).hex())
CORS(app, supports_credentials=True)

# Directory where .txt exports are saved
EXPORT_DIR = pathlib.Path(os.environ.get("STORYBOT_EXPORT_DIR", "exports"))
EXPORT_DIR.mkdir(exist_ok=True)

# Per-process MeWe client (holds cookies/session state)
_mewe_client: MeWeClient | None = None


def _get_mewe_client() -> MeWeClient:
    global _mewe_client
    if _mewe_client is None:
        _mewe_client = MeWeClient()
        # Try to restore saved cookies
        saved = db.get_setting("mewe_cookies", "")
        if saved:
            try:
                _mewe_client.load_session_cookies(json.loads(saved))
            except Exception:
                pass
    return _mewe_client


def _get_discord_client() -> DiscordClient:
    token = db.get_setting("discord_token", "")
    if not token:
        raise ValueError("Discord user token not set. Please configure it in Settings.")
    return DiscordClient(token)


def _detect_source(url: str) -> str:
    try:
        hostname = urlparse(url.strip()).hostname or ""
    except Exception:
        hostname = ""
    # Strip leading 'www.' for comparison
    hostname = hostname.lower().removeprefix("www.")
    if hostname == "mewe.com" or hostname.endswith(".mewe.com"):
        return "mewe"
    if hostname in ("discord.com", "discordapp.com") or \
       hostname.endswith(".discord.com") or hostname.endswith(".discordapp.com"):
        return "discord"
    raise ValueError("Unsupported URL. Only MeWe and Discord links are supported.")


def _save_to_txt(world_name: str, title: str, content: str, url: str) -> str:
    """Write content to a .txt file and return the path."""
    safe_world = "".join(c if c.isalnum() or c in " _-" else "_" for c in world_name)
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title[:60])
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_world}__{safe_title}__{ts}.txt"
    # Resolve and verify the path stays within EXPORT_DIR
    filepath = (EXPORT_DIR / filename).resolve()
    if not str(filepath).startswith(str(EXPORT_DIR.resolve())):
        raise ValueError("Invalid export path.")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Source: {url}\n")
        f.write(f"Exported: {datetime.utcnow().isoformat()} UTC\n")
        f.write("=" * 60 + "\n\n")
        f.write(content)

    return str(filepath)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/ping")
def ping():
    return jsonify({"ok": True})


# ── Worlds ─────────────────────────────────────────────────────────────────────

@app.route("/api/worlds", methods=["GET"])
def list_worlds():
    return jsonify(db.get_worlds())


@app.route("/api/worlds", methods=["POST"])
def create_world():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "World name is required."}), 400
    try:
        world_id = db.create_world(name, body.get("description", ""))
        return jsonify({"id": world_id, "name": name}), 201
    except Exception:
        return jsonify({"error": "World name already exists or could not be saved."}), 400


@app.route("/api/worlds/<int:world_id>", methods=["DELETE"])
def delete_world(world_id):
    db.delete_world(world_id)
    return jsonify({"ok": True})


@app.route("/api/worlds/<int:world_id>", methods=["PATCH"])
def update_world(world_id):
    body = request.get_json(force=True)
    db.update_world(world_id, name=body.get("name"), description=body.get("description"))
    return jsonify({"ok": True})


# ── Stories ────────────────────────────────────────────────────────────────────

@app.route("/api/worlds/<int:world_id>/stories", methods=["GET"])
def list_stories(world_id):
    stories = db.get_stories(world_id)
    # Don't send full raw_content in list view (can be large)
    for s in stories:
        s.pop("raw_content", None)
    return jsonify(stories)


@app.route("/api/stories/<int:story_id>", methods=["GET"])
def get_story(story_id):
    story = db.get_story(story_id)
    if story is None:
        return jsonify({"error": "Story not found."}), 404
    return jsonify(story)


@app.route("/api/stories/<int:story_id>", methods=["DELETE"])
def delete_story(story_id):
    db.delete_story(story_id)
    return jsonify({"ok": True})


# ── Characters ─────────────────────────────────────────────────────────────────

@app.route("/api/worlds/<int:world_id>/characters", methods=["GET"])
def list_characters(world_id):
    return jsonify(db.get_characters(world_id))


# ── Process link ───────────────────────────────────────────────────────────────

@app.route("/api/process", methods=["POST"])
def process_link():
    """
    Body:
      {
        "url": "...",
        "world_id": 1,
        "mode": "ai" | "text",   // ai = analyze with AI; text = save to txt only
      }
    """
    body = request.get_json(force=True)
    url = (body.get("url") or "").strip()
    world_id = body.get("world_id")
    mode = body.get("mode", "ai")

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not world_id:
        return jsonify({"error": "world_id is required."}), 400

    # Detect platform
    try:
        platform = _detect_source(url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Fetch content
    try:
        if platform == "mewe":
            client = _get_mewe_client()
            post_data = client.fetch_post(url)
            raw_text = MeWeClient.format_as_text(post_data)
            title = post_data.get("title", "Untitled MeWe Post")
            source_type = "mewe_post"
        else:
            client = _get_discord_client()
            thread_data = client.fetch_thread(url)
            raw_text = DiscordClient.format_as_text(thread_data)
            title = thread_data.get("title", "Untitled Discord Thread")
            source_type = f"discord_{thread_data.get('channel_type', 'thread')}"
    except PermissionError as e:
        return jsonify({"error": str(e), "auth_required": platform}), 401
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "Failed to fetch content. Check that the URL is correct and you are logged in."}), 500

    # Get world name for file naming
    worlds = {w["id"]: w["name"] for w in db.get_worlds()}
    world_name = worlds.get(world_id, f"world_{world_id}")

    txt_path = ""
    ai_analysis = {}

    if mode == "text":
        # Save to .txt only
        try:
            txt_path = _save_to_txt(world_name, title, raw_text, url)
        except Exception:
            return jsonify({"error": "Could not save export file. Check that the exports directory is writable."}), 500

    else:
        # AI analysis
        settings = db.get_all_settings()
        ai_backend = settings.get("ai_backend", "ollama")
        ai_model = settings.get("ai_model", "")
        openai_key = settings.get("openai_api_key", "")

        try:
            ai_analysis = analyzer.analyze_story(
                raw_text,
                backend=ai_backend,
                api_key=openai_key or None,
                model=ai_model or None,
            )
        except Exception:
            # Non-fatal: store raw content without analysis
            ai_analysis = {"error": "AI analysis failed. Check your AI backend settings."}

        # Update world bible
        if ai_analysis and "error" not in ai_analysis:
            try:
                existing_bible_json = settings.get("world_bible", "{}")
                world_bibles = json.loads(existing_bible_json) if existing_bible_json else {}
                current_bible = world_bibles.get(str(world_id), {})
                updated_bible = analyzer.update_world_bible(
                    current_bible, ai_analysis, raw_text,
                    backend=ai_backend, api_key=openai_key or None, model=ai_model or None,
                )
                world_bibles[str(world_id)] = updated_bible
                db.set_setting("world_bible", json.dumps(world_bibles))

                # Upsert characters into DB
                for char in ai_analysis.get("characters", []):
                    if char.get("name"):
                        db.upsert_character(
                            world_id, char["name"],
                            description=char.get("description", ""),
                        )
            except Exception:
                pass  # Bible update failure is non-fatal

        # Also save .txt alongside AI analysis
        try:
            txt_path = _save_to_txt(world_name, title, raw_text, url)
        except Exception:
            pass

    # Persist story
    story_id = db.create_story(
        world_id=world_id,
        source_url=url,
        source_type=source_type,
        title=title,
        raw_content=raw_text,
        ai_analysis=ai_analysis,
        txt_path=txt_path,
    )

    return jsonify({
        "story_id": story_id,
        "title": title,
        "source_type": source_type,
        "txt_path": txt_path,
        "ai_analysis": ai_analysis,
    })


# ── World bible ────────────────────────────────────────────────────────────────

@app.route("/api/worlds/<int:world_id>/bible", methods=["GET"])
def get_world_bible(world_id):
    raw = db.get_setting("world_bible", "{}")
    try:
        bibles = json.loads(raw)
    except Exception:
        bibles = {}
    return jsonify(bibles.get(str(world_id), {}))


# ── MeWe auth ──────────────────────────────────────────────────────────────────

@app.route("/api/auth/mewe/login", methods=["POST"])
def mewe_login():
    body = request.get_json(force=True)
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    client = _get_mewe_client()
    result = client.login_with_password(email, password)
    if result.get("success"):
        db.set_setting("mewe_cookies", json.dumps(client.get_session_cookies()))
        return jsonify({"ok": True, "message": "Logged in to MeWe."})
    return jsonify({"error": result.get("error", "Login failed.")}), 401


@app.route("/api/auth/mewe/start", methods=["POST"])
def mewe_start():
    body = request.get_json(force=True)
    phone = (body.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Phone number is required."}), 400
    client = _get_mewe_client()
    result = client.start_phone_login(phone)
    if result["status"] in (200, 201):
        return jsonify({"ok": True, "message": "SMS sent. Enter the code."})
    return jsonify({"error": result["data"].get("message", "Failed to send SMS.")}), 400


@app.route("/api/auth/mewe/verify", methods=["POST"])
def mewe_verify():
    body = request.get_json(force=True)
    otp = (body.get("otp") or "").strip()
    if not otp:
        return jsonify({"error": "OTP code is required."}), 400
    client = _get_mewe_client()
    result = client.verify_otp(otp)
    if result.get("success"):
        # Save cookies for session persistence
        db.set_setting("mewe_cookies", json.dumps(client.get_session_cookies()))
        return jsonify({"ok": True, "message": "Logged in to MeWe."})
    return jsonify({"error": result.get("error", "Verification failed.")}), 401


@app.route("/api/auth/mewe/status", methods=["GET"])
def mewe_status():
    client = _get_mewe_client()
    return jsonify({"authenticated": client.is_authenticated()})


@app.route("/api/auth/mewe/logout", methods=["POST"])
def mewe_logout():
    global _mewe_client
    _mewe_client = None
    db.set_setting("mewe_cookies", "")
    return jsonify({"ok": True})


# ── Discord auth ───────────────────────────────────────────────────────────────

@app.route("/api/auth/discord", methods=["POST"])
def discord_auth():
    body = request.get_json(force=True)
    token = (body.get("token") or "").strip()
    if not token:
        return jsonify({"error": "Discord token is required."}), 400
    client = DiscordClient(token)
    if not client.is_authenticated():
        return jsonify({"error": "Token is invalid or expired."}), 401
    db.set_setting("discord_token", token)
    return jsonify({"ok": True, "message": "Discord token saved."})


@app.route("/api/auth/discord/status", methods=["GET"])
def discord_status():
    token = db.get_setting("discord_token", "")
    if not token:
        return jsonify({"authenticated": False})
    client = DiscordClient(token)
    return jsonify({"authenticated": client.is_authenticated()})


@app.route("/api/auth/discord/logout", methods=["POST"])
def discord_logout():
    db.set_setting("discord_token", "")
    return jsonify({"ok": True})


# ── Settings ───────────────────────────────────────────────────────────────────

@app.route("/api/settings", methods=["GET"])
def get_settings():
    s = db.get_all_settings()
    # Redact sensitive values
    redacted = {}
    for k, v in s.items():
        if k in ("mewe_cookies", "discord_token", "openai_api_key", "world_bible"):
            redacted[k] = "***" if v else ""
        else:
            redacted[k] = v
    return jsonify(redacted)


@app.route("/api/settings", methods=["POST"])
def save_settings():
    body = request.get_json(force=True)
    allowed = {"ai_backend", "ai_model", "openai_api_key", "export_dir"}
    for key in allowed:
        if key in body:
            db.set_setting(key, str(body[key]))
    return jsonify({"ok": True})


# ── Bootstrap ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  StoryBot running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
