# StoryBot

A local web application that reads posts from **MeWe** and threads/forums from **Discord**, uses AI to build a shared understanding of characters and overarching story arcs, and organises everything into separate **Worlds**.

---

## Features

| Feature | Details |
|---|---|
| **MeWe** | Log in with your phone number (SMS OTP). Fetches post body + all comments. |
| **Discord** | Log in with your user token. Fetches entire threads and forum posts (all messages, paginated). |
| **AI mode** | Analyses story text to extract characters, themes, plot points, and a story arc. Builds a cumulative *World Bible* across all stories in a world. |
| **Text-save mode** | Toggle on to skip AI and just save everything to a `.txt` file in `exports/`. |
| **Worlds** | Organise stories into separate worlds/universes. Each world has its own character list and World Bible. |
| **Images ignored** | Only text content is fetched; images and attachments are skipped. |

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. (Optional) Set up Ollama for local AI

Install [Ollama](https://ollama.com/) and pull a model:

```bash
ollama pull llama3
```

Ollama is the default AI backend — no API key required.

### 3. Run the app

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Configuration

All settings are stored in `storybot.db` (SQLite).

### AI backends

| Backend | How to set up |
|---|---|
| **Ollama** (default) | Install Ollama, pull a model (`ollama pull llama3`), then just start the app. |
| **OpenAI** | Select "OpenAI" in Settings, enter your API key and a model name (e.g. `gpt-4o-mini`). |
| **None** | Disables AI; all processing is text-save only. |

### MeWe login

1. Click **Credentials → MeWe**.
2. Enter your phone number (with country code, e.g. `+1 555 000 0000`).
3. Click **Send SMS** and wait for the code.
4. Enter the code and click **Verify**.

Your session cookies are saved in the database so you won't need to log in again.

### Discord user token

> ⚠️ Discord ToS prohibits automated self-bot usage. Use this tool for **personal archival** only.

1. Open Discord in your browser.
2. Open DevTools → **Application** → **Local Storage** → `https://discord.com`.
3. Find the key **`token`** and copy its value (without quotes).
4. In StoryBot, go to **Credentials → Discord** and paste the token.

---

## Usage

1. **Create a World** — click **+** in the sidebar and give it a name.
2. **Paste a link** — MeWe post URL or Discord thread/forum URL.
3. **Choose mode**:
   - **AI** (default) — fetches content and runs AI analysis; characters are added to the world.
   - **Text** (toggle on) — fetches content and saves a `.txt` file only.
4. Click **Process**.

Saved `.txt` files are written to the `exports/` directory next to `app.py`.

---

## Supported URL formats

### MeWe
```
https://mewe.com/p/{userId}/{postId}
https://mewe.com/group/{groupId}/post/{postId}
https://mewe.com/{username}/{postId}
```

### Discord
```
https://discord.com/channels/{guild}/{channel}
https://discord.com/channels/{guild}/{channel}/{thread_id}
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | Port the web server listens on |
| `STORYBOT_DB` | `storybot.db` | Path to SQLite database |
| `STORYBOT_EXPORT_DIR` | `exports` | Directory for `.txt` exports |
| `SECRET_KEY` | random | Flask session secret key |

---

## Notes

- The MeWe API is **unofficial** and reverse-engineered. It may break if MeWe changes their API.
- Discord user-token access is a **self-bot** and violates Discord's ToS if misused. This app is intended for personal archival only.
- AI analysis is performed locally (Ollama) by default and never sends data to external services unless you configure the OpenAI backend.