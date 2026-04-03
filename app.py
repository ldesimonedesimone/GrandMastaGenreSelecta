import os
import re
import hashlib
import hmac
import time
from urllib.parse import quote
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Deterministic SKU → genre (no LLM) ───────────────────────────────────────
# Genres styled like EveryNoise.com (lowercase); same SKU always maps the same way.
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
    return {"genre": genre, "sku_meaning": sku_meaning, "connection": conn}


def extract_sku(raw: str) -> str:
    s = raw.strip()
    m = re.search(r"mcmaster\.com/([A-Za-z0-9]{4,12})(?:/|$|\?)", s, re.I)
    if m:
        return m.group(1).upper()
    return "".join(c for c in s if c.isalnum()).upper()


# ── Spotify search (genre in search box). Do not use /playlists in the path — the native
# iOS/iPadOS app mis-handles it and puts the word "playlists" in the search field. Web can
# still switch to the Playlists tab after opening /search/{q}.
def spotify_search_url(query: str) -> str:
    q = quote(query, safe="")
    return f"https://open.spotify.com/search/{q}"


def spotify_web_link(genre: str) -> str:
    return spotify_search_url(genre)


def spotify_deep_link(genre: str) -> str:
    return spotify_search_url(genre)

# ── EveryNoise link builder ──────────────────────────────────────────────────
def everynoise_link(genre: str) -> str:
    """Build an EveryNoise.com link for the genre."""
    slug = genre.replace(" ", "")  # EveryNoise removes spaces in anchors
    return f"https://everynoise.com/#{slug}"

# ── Slack signature verification ─────────────────────────────────────────────
def verify_slack_signature(request) -> bool:
    """Verify the request actually came from Slack."""
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return True  # Skip verification if secret not configured (dev mode)

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    # Reject requests older than 5 minutes
    if abs(time.time() - int(timestamp)) > 300:
        return False

    sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)

# ── Slack message builder ────────────────────────────────────────────────────
def build_slack_message(sku: str, result: dict) -> dict:
    genre = result["genre"]
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
                        "text": f"*McMaster-Carr SKU:*\n`{sku}`",
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
                        "text": f"Tip: <{spotify_deep_link(genre)}|Open Spotify search> — same link as the button. On the website, switch to *Playlists*; in the mobile app, tap *Playlists* after search opens.",
                    }
                ],
            },
        ],
    }


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "app": "GrandMastaGenreSelecta",
        "status": "running",
        "health": "/health",
        "slack_command_url": "/grandmastagenreselecta",
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/grandmastagenreselecta", methods=["POST"])
def grandmasta_genre_selecta():
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    # Get SKU from slash command text, e.g. /grandmastagenreselecta 91251A307
    # Strip quotes / punctuation so "5621N15" and pasted URLs still work.
    sku = extract_sku(request.form.get("text", ""))

    if not sku:
        return jsonify({
            "response_type": "ephemeral",
            "text": (
                "👋 Please provide a SKU from your McMaster-Carr catalog.\n"
                "Usage: `/grandmastagenreselecta 91251A307`"
            ),
        })

    # Basic SKU validation — alphanumeric, 4–12 characters
    if not sku.isalnum() or not (4 <= len(sku) <= 12):
        return jsonify({
            "response_type": "ephemeral",
            "text": (
                f"⚠️ `{sku}` doesn't look like a valid McMaster-Carr SKU.\n"
                "SKUs are alphanumeric and typically 6–10 characters, e.g. `91251A307`.\n"
                "Try again with a SKU from your catalog."
            ),
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
