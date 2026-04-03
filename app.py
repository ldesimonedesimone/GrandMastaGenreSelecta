import os
import hashlib
import hmac
import time
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)

# ── Clients ────────────────────────────────────────────────────────────────
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Claude: SKU → genre mapping ─────────────────────────────────────────────
def sku_to_genre(sku: str) -> dict:
    """
    Ask Claude to creatively map a McMaster-Carr SKU to a music genre
    from EveryNoise.com. Returns a dict with genre + reasoning.
    """
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

Respond with ONLY valid JSON in this exact format (no markdown, no extra text):
{{
  "genre": "the genre name",
  "sku_meaning": "one sentence on what the SKU 'means'",
  "connection": "one sentence on why this SKU maps to this genre"
}}"""

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = message.content[0].text.strip()
    return json.loads(raw)

# ── Spotify deep link builder ────────────────────────────────────────────────
def spotify_deep_link(genre: str) -> str:
    """Build a Spotify search deep link for the genre."""
    encoded = genre.replace(" ", "%20")
    return f"spotify:search:{encoded}"

def spotify_web_link(genre: str) -> str:
    """Build a Spotify web search URL for the genre."""
    encoded = genre.replace(" ", "%20")
    return f"https://open.spotify.com/search/{encoded}/genres"

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
                        "text": {"type": "plain_text", "text": "🎧 Open in Spotify", "emoji": True},
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
                        "text": f"Tip: Copy <{spotify_deep_link(genre)}|this deep link> to open Spotify directly.",
                    }
                ],
            },
        ],
    }

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/grandmastagenreselecta", methods=["POST"])
def grandmasta_genre_selecta():
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    # Get SKU from slash command text, e.g. /grandmastagenreselecta 91251A307
    sku = request.form.get("text", "").strip().upper()

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
            "text": f"⚠️ Something went wrong generating today's genre: {str(e)}",
        })

    message = build_slack_message(sku, result)
    return jsonify(message)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)
