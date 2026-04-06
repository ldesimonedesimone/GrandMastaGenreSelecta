import html
import json
import os
import re
import hashlib
import hmac
import threading
import time
from urllib.parse import quote

import requests
from anthropic import Anthropic
from flask import Flask, Response, jsonify, redirect, request

app = Flask(__name__)

# ── Deterministic SKU → genre (no LLM) ───────────────────────────────────────
_GENRES = (
    "vapor twitch",
    "dark clubbing",
    "deep nordic folk",
    "industrial metal",
    "labor day",
    "float house",
    "dungeon synth",
    "slow motion techno",
    "organic ambient",
    "post-dubstep",
    "shoegaze",
    "math rock",
    "garage psych",
    "stomp and holler",
    "future funk",
    "wonky",
    "microhouse",
    "deep disco",
    "cold wave",
    "space rock",
    "art pop",
    "neo-psychedelic",
    "chamber psych",
    "downtempo",
    "trip hop",
    "big beat",
    "breakcore",
    "footwork",
    "uk funky",
    "balearic",
    "tropical house",
    "progressive trance",
    "melodic techno",
    "minimal wave",
    "noise rock",
    "post-punk revival",
    "sludge metal",
    "stoner rock",
    "bluegrass",
    "outlaw country",
    "neo-soul",
    "future garage",
    "uk drill",
    "boom bap",
    "abstract hip hop",
    "jazz rap",
    "spiritual jazz",
    "latin jazz",
    "afrobeat",
    "highlife",
)

_MATERIALS = (
    "cold-rolled patience",
    "chrome vanadium attitude",
    "black oxide mystery",
    "passivated calm",
    "nylon quiet",
    "brass-forward swagger",
    "silicone slip",
    "steel certainty",
    "aluminum lightness",
    "stainless resolve",
)

_FORMS = (
    "socket head cap energy",
    "wave-spring tension",
    "thrust-washer diplomacy",
    "set-screw honesty",
    "retaining-ring drama",
    "shoulder-bolt posture",
    "hex nut certainty",
    "threaded insert patience",
    "spacer sleeve poise",
    "cotter pin loyalty",
)

_MOODS = (
    "tight tolerances",
    "catalog gravity",
    "bin-location clarity",
    "±0.001 vibes",
    "reorder-point melancholy",
    "bulk-pack euphoria",
    "line-item poetry",
)

_CONN = (
    "The checksum that fingerprinted `{sku}` also landed on _{genre}_ — same warehouse, different aisle.",
    "`{sku}` hashes to the same shelf bin as _{genre}_: hardware on the outside, BPM on the inside.",
    "Digits and letters in `{sku}` routed the pick list straight to _{genre}_.",
    "If this SKU were a bin label, the listening bin next to it would be _{genre}_.",
)


def _sku_entropy(sku: str) -> int:
    return int(hashlib.sha256(sku.encode("utf-8")).hexdigest(), 16)


def sku_to_genre(sku: str) -> dict:
    h = _sku_entropy(sku)
    genre = _GENRES[h % len(_GENRES)]

    letters = "".join(c for c in sku if c.isalpha()) or "null"
    digits = "".join(c for c in sku if c.isdigit()) or "0"
    m = _MATERIALS[(h // 7) % len(_MATERIALS)]
    f = _FORMS[(h // 13) % len(_FORMS)]
    mood = _MOODS[(h // 19) % len(_MOODS)]
    sku_meaning = (
        f"Letters `{letters}` × digits `{digits}` → {m}, {f}, {mood}."
    )

    conn = _CONN[(h // 23) % len(_CONN)].format(sku=sku, genre=genre)
    return {
        "genre": genre,
        "sku_meaning": sku_meaning,
        "connection": conn,
        "engine": "hash",
    }


def sku_to_genre_anthropic(sku: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    prompt = f"""You are a creative DJ who works at an industrial supply warehouse.
Your job is to map McMaster-Carr hardware SKUs to music genres from EveryNoise.com.

The SKU is: {sku}

Rules:
1. Decode the SKU creatively — the numbers and letters can suggest material, size,
   application, texture, weight, era, or vibe.
2. Map it to a real genre from EveryNoise.com (e.g. "vapor twitch", "dark clubbing",
   "deep nordic folk", "industrial metal", "labor day", etc.)
3. The connection should be surprising, funny, or poetic — not obvious.
4. Keep the genre name lowercase, exactly as it would appear on everynoise.com.
5. Do not mention AI vendors, chatbots, or model names in the JSON string values.

Respond with ONLY valid JSON in this exact format (no markdown, no extra text):
{{
  "genre": "the genre name",
  "sku_meaning": "one sentence on what the SKU 'means'",
  "connection": "one sentence on why this SKU maps to this genre"
}}"""

    client = Anthropic(api_key=key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    out = json.loads(raw)
    out["engine"] = "anthropic"
    return out


def extract_sku(raw: str) -> str:
    s = raw.strip()
    m = re.search(r"mcmaster\.com/([A-Za-z0-9]{4,12})(?:/|$|\?)", s, re.I)
    if m:
        return m.group(1).upper()
    return "".join(c for c in s if c.isalnum()).upper()


def _engine_path() -> str:
    return os.environ.get("ENGINE_MODE_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".engine_mode",
    )


def get_engine_mode() -> str:
    default = os.environ.get("ENGINE_DEFAULT", "hash").strip().lower()
    if default not in ("hash", "anthropic"):
        default = "hash"
    p = _engine_path()
    try:
        with open(p, encoding="utf-8") as f:
            v = f.read().strip().lower()
            if v in ("hash", "anthropic"):
                return v
    except FileNotFoundError:
        pass
    return default


def set_engine_mode(mode: str) -> None:
    mode = mode.strip().lower()
    assert mode in ("hash", "anthropic")
    p = _engine_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(mode)


def _admin_token_ok(provided: str | None) -> bool:
    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if not expected:
        return True
    return (provided or "").strip() == expected


def spotify_search_url(query: str) -> str:
    q = quote(query, safe="")
    return f"https://open.spotify.com/search/{q}"


def spotify_web_link(genre: str) -> str:
    return spotify_search_url(genre)


def spotify_deep_link(genre: str) -> str:
    return spotify_search_url(genre)


def everynoise_link(genre: str) -> str:
    slug = genre.replace(" ", "")
    return f"https://everynoise.com/#{slug}"


def mcmaster_product_url(sku: str) -> str:
    return f"https://www.mcmaster.com/{sku}/"


def verify_slack_signature(request) -> bool:
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return True

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if abs(time.time() - int(timestamp)) > 300:
        return False

    sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def build_slack_message(sku: str, result: dict) -> dict:
    genre = result["genre"]
    mcm = mcmaster_product_url(sku)
    sku_block = f"*McMaster-Carr SKU:*\n<{mcm}|McMaster Item> · `{sku}`"
    return {
        "response_type": "in_channel",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔩 GrandMastaGenreSelecta 🎵",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": sku_block,
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Genre of the Day:*\n_{genre}_",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*SKU Decoded:* {result['sku_meaning']}\n"
                        f"*Why this genre:* {result['connection']}"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🎧 Search in Spotify", "emoji": True},
                        "url": spotify_web_link(genre),
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🗺️ Explore on EveryNoise", "emoji": True},
                        "url": everynoise_link(genre),
                    },
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Tip: <{spotify_deep_link(genre)}|Open Spotify search> — same link as the button. "
                            "On the website, switch to *Playlists*; in the mobile app, tap *Playlists* after search opens."
                        ),
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Spotify *Jam* invite links are created in the app when someone starts a Jam; "
                            "there is no public URL this bot can generate for “join jam” ahead of time."
                        ),
                    },
                ],
            },
        ],
    }


def _post_slack_delayed(response_url: str, sku: str) -> None:
    try:
        result = sku_to_genre_anthropic(sku)
        payload = build_slack_message(sku, result)
        requests.post(response_url, json=payload, timeout=60)
    except Exception as e:
        requests.post(
            response_url,
            json={
                "response_type": "ephemeral",
                "text": f"⚠️ Mapping failed: {str(e)}",
            },
            timeout=30,
        )


def _html_dashboard() -> str:
    mode = get_engine_mode()
    need_token = bool(os.environ.get("ADMIN_TOKEN", "").strip())
    token_hint = (
        "<p>Set <code>ADMIN_TOKEN</code> in the environment; use the form below with the token (quick links are disabled).</p>"
        if need_token
        else "<p><em>No <code>ADMIN_TOKEN</code> — quick links work; fine for local dev only.</em></p>"
    )
    base = request.url_root.rstrip("/")
    h_sel = " selected" if mode == "hash" else ""
    a_sel = " selected" if mode == "anthropic" else ""
    quick = ""
    if not need_token:
        quick = f"""<p>
<a class="button" href="{html.escape(base)}/?set=hash">Use hash</a>
<a class="button" href="{html.escape(base)}/?set=anthropic">Use Anthropic</a>
</p>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GrandMastaGenreSelecta</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }}
code {{ background: #eee; padding: 0.1em 0.3em; border-radius: 4px; }}
a.button {{ display: inline-block; margin: 0.25rem 0.5rem 0.25rem 0; padding: 0.5rem 0.75rem;
  background: #222; color: #fff; text-decoration: none; border-radius: 6px; }}
footer {{ margin-top: 2rem; font-size: 0.9rem; color: #555; }}
</style>
</head>
<body>
<h1>GrandMastaGenreSelecta</h1>
<p>Active mapping engine: <strong>{html.escape(mode)}</strong></p>
<p><code>hash</code> = fast deterministic mapping. <code>anthropic</code> = cloud LLM mapping (needs <code>ANTHROPIC_API_KEY</code>; Slack uses async reply to avoid timeout).</p>
{token_hint}
{quick}
<form method="post" action="{html.escape(base)}/" style="margin-top:1rem;">
<label>Switch via form<br/>
<select name="mode">
<option value="hash"{h_sel}>hash</option>
<option value="anthropic"{a_sel}>anthropic</option>
</select></label>
<p><label>Admin token (if <code>ADMIN_TOKEN</code> is set): <input name="token" type="password" autocomplete="off" style="width:100%;max-width:20rem"/></label></p>
<button type="submit">Save engine</button>
</form>
<footer>
<p>JSON: <a href="{html.escape(base)}/status"><code>/status</code></a></p>
</footer>
</body>
</html>"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        m = request.form.get("mode", "").strip().lower()
        if m in ("hash", "anthropic") and _admin_token_ok(request.form.get("token")):
            set_engine_mode(m)
        return redirect("/")

    if request.args.get("set") in ("hash", "anthropic"):
        if _admin_token_ok(request.args.get("token")):
            set_engine_mode(request.args.get("set", ""))
        return redirect("/")

    return Response(_html_dashboard(), mimetype="text/html")


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "app": "GrandMastaGenreSelecta",
        "status": "running",
        "engine": get_engine_mode(),
        "health": "/health",
        "slack_command_url": "/grandmastagenreselecta",
        "admin_token_required": bool(os.environ.get("ADMIN_TOKEN", "").strip()),
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/grandmastagenreselecta", methods=["POST"])
def grandmasta_genre_selecta():
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    sku = extract_sku(request.form.get("text", ""))

    if not sku:
        return jsonify({
            "response_type": "ephemeral",
            "text": (
                "👋 Please provide a SKU from your McMaster-Carr catalog.\n"
                "Usage: `/grandmastagenreselecta 91251A307`"
            ),
        })

    if not sku.isalnum() or not (4 <= len(sku) <= 12):
        return jsonify({
            "response_type": "ephemeral",
            "text": (
                f"⚠️ `{sku}` doesn't look like a valid McMaster-Carr SKU.\n"
                "SKUs are alphanumeric and typically 6–10 characters, e.g. `91251A307`.\n"
                "Try again with a SKU from your catalog."
            ),
        })

    engine = get_engine_mode()

    if engine == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return jsonify({
                "response_type": "ephemeral",
                "text": "⚠️ Anthropic mode is on but `ANTHROPIC_API_KEY` is not set in the server environment.",
            })

        response_url = request.form.get("response_url", "")
        if not response_url:
            return jsonify({"error": "Missing response_url"}), 400

        threading.Thread(
            target=_post_slack_delayed,
            args=(response_url, sku),
            daemon=True,
        ).start()

        return jsonify({
            "response_type": "ephemeral",
            "text": "⏳ Mapping your SKU… (this can take a few seconds)",
        })

    try:
        result = sku_to_genre(sku)
    except Exception as e:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"⚠️ Something went wrong: {str(e)}",
        })

    return jsonify(build_slack_message(sku, result))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)
