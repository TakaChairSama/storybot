"""AI story analyzer.

Supported backends:
  - ollama   (default, local, no API key needed)
  - openai   (requires OPENAI_API_KEY in settings)
  - none     (disabled — text-save mode)

The analyzer takes raw story text and:
  1. Extracts characters with brief descriptions.
  2. Identifies themes and plot points.
  3. Merges new info into the world's existing knowledge base.
"""
import json
import re
from typing import Optional


SYSTEM_PROMPT = """You are a literary analyst helping build a "world bible" for a shared fictional universe.
Given raw story text, you will:
1. Extract all named characters with a brief description of their role/personality.
2. Identify key themes, plot points, and story arcs.
3. Note any relationships between characters.
4. Summarize the piece in 2-3 sentences.

Respond ONLY with valid JSON in this exact structure:
{
  "summary": "...",
  "characters": [
    {"name": "...", "description": "...", "relationships": ["..."]}
  ],
  "themes": ["..."],
  "plot_points": ["..."],
  "story_arc": "..."
}"""

UPDATE_SYSTEM_PROMPT = """You are a literary analyst maintaining a "world bible" for a fictional universe.
You will be given:
  - The current world bible (existing knowledge).
  - New story content just fetched.
Merge the new information into the world bible, updating characters, themes, and the overall arc.

Respond ONLY with valid JSON in the same structure as the world bible:
{
  "overview": "...",
  "characters": [
    {"name": "...", "description": "...", "relationships": ["..."]}
  ],
  "themes": ["..."],
  "story_arcs": ["..."],
  "timeline": ["..."]
}"""


def _call_ollama(prompt: str, system: str, model: str = "llama3") -> str:
    try:
        import ollama  # type: ignore
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response["message"]["content"]
    except ImportError:
        raise RuntimeError("ollama Python package not installed. Run: pip install ollama")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


def _call_openai(prompt: str, system: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except ImportError:
        raise RuntimeError("openai Python package not installed. Run: pip install openai")
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}")


def _parse_json_response(text: str) -> dict:
    """Extract JSON from a model response (handles markdown code blocks)."""
    text = text.strip()
    # Strip ```json ... ``` wrapper if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        # Best-effort: return raw text in a wrapper
        return {"raw_response": text, "error": "Could not parse JSON from AI response"}


def analyze_story(
    raw_text: str,
    backend: str = "ollama",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Analyze a single story text.
    Returns a dict with characters, themes, plot_points, summary, story_arc.
    """
    if backend == "none" or not raw_text.strip():
        return {}

    prompt = f"Analyze the following story text:\n\n{raw_text[:12000]}"
    # 12000 characters keeps the prompt within most models' context windows
    # while covering the substantial majority of a typical post + comments.

    if backend == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is required for the 'openai' backend.")
        result = _call_openai(prompt, SYSTEM_PROMPT, api_key, model or "gpt-4o-mini")
    else:
        result = _call_ollama(prompt, SYSTEM_PROMPT, model or "llama3")

    return _parse_json_response(result)


def update_world_bible(
    world_bible: dict,
    new_story_analysis: dict,
    new_raw_text: str,
    backend: str = "ollama",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Merge a new story's analysis into the world bible.
    Returns the updated world bible dict.
    """
    if backend == "none":
        return world_bible

    bible_json = json.dumps(world_bible, indent=2)
    story_json = json.dumps(new_story_analysis, indent=2)

    prompt = (
        f"CURRENT WORLD BIBLE:\n{bible_json}\n\n"
        f"NEW STORY ANALYSIS:\n{story_json}\n\n"
        f"NEW STORY EXCERPT (first 3000 chars):\n{new_raw_text[:3000]}\n\n"
        "Merge the new information into the world bible."
    )

    if backend == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is required for the 'openai' backend.")
        result = _call_openai(prompt, UPDATE_SYSTEM_PROMPT, api_key, model or "gpt-4o-mini")
    else:
        result = _call_ollama(prompt, UPDATE_SYSTEM_PROMPT, model or "llama3")

    return _parse_json_response(result)
