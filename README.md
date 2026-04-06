# GrandMastaGenreSelecta

A Slack slash command that maps a McMaster-Carr SKU to a music genre in the style of [EveryNoise.com](https://everynoise.com), then posts to Slack with **Spotify search** and EveryNoise links.

**Mapping engine (toggle on the web):**
- **`hash`** (default) — fast deterministic mapping (no API calls).
- **`anthropic`** — Claude maps the SKU (needs `ANTHROPIC_API_KEY`). Slack gets an instant “working…” message, then the full card via `response_url` so you avoid **Slack’s ~3s slash-command timeout**.

Open **`/`** on your deployed app for a small control panel; **`/status`** returns JSON including the active engine.

Spotify uses `/search/{query}` only (no `/playlists` path) so the native iPad/iPhone app does not put the word `playlists` in the search bar.

**Example output:**
> 🔩 **GrandMastaGenreSelecta** 🎵
> SKU: `91251A307` → Genre: *deep nordic folk*
> SKU Decoded: Letters `A` × digits `91251307` → chrome vanadium attitude, hex nut certainty, catalog gravity.
> Why this genre: The checksum that fingerprinted `91251A307` also landed on *deep nordic folk* — same warehouse, different aisle.
> [🎧 Search in Spotify] [🗺️ Explore on EveryNoise]

---

## How It Works

1. You type `/grandmastagenreselecta` followed by a SKU from your physical McMaster-Carr catalog
2. Either the **hash** engine or **Claude** maps the SKU to a genre (see engine toggle on `/`)
3. A message is posted to your channel with the SKU, genre, text, and links

---

## Setup

### 1. Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name it "GrandMastaGenreSelecta", pick your workspace
3. Go to **Slash Commands** → **Create New Command**
   - Command: `/grandmastagenreselecta`
   - Request URL: `https://YOUR-APP-URL/grandmastagenreselecta` *(fill in after deploying)*
   - Short Description: "Pick today's genre from a McMaster SKU"
   - Usage Hint: `[SKU]  e.g. 91251A307`
4. Go to **OAuth & Permissions** → add these scopes:
   - `commands`
   - `chat:write`
5. Go to **Basic Information** → copy the **Signing Secret** → save as `SLACK_SIGNING_SECRET`
6. **Install App** to your workspace

---

### 2. Run Locally (for testing)

```bash
# Clone / copy the project files
cd GrandMastaGenreSelecta

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your actual keys

# Load env vars and run
export $(cat .env | xargs)
python app.py
```

The app runs on `http://localhost:3000`.

Slack only accepts **public HTTPS URLs** for the slash command (no `localhost`). Use a tunnel so Slack can reach your machine:

**Option 1 — ngrok** (sign up for a free account at [ngrok.com](https://ngrok.com)):
```bash
ngrok http 3000
```
Copy the `https://xxxx.ngrok-free.app` URL and set your Slack Request URL to `https://xxxx.ngrok-free.app/grandmastagenreselecta`.

**Option 2 — localtunnel** (no account):
```bash
npx localtunnel --port 3000
```
Use the printed URL (e.g. `https://something.loca.lt`) plus `/grandmastagenreselecta` as the Request URL. If the tunnel page asks "Click to continue", you may need to send a custom header; ngrok is simpler if that bothers you.

**Option 3 — deploy first**  
Deploy to Railway or Render (see below), then use the app’s live URL as the Request URL. Easiest if you don’t want to run a tunnel.

---

### 3. Deploy (Pick One)

#### Option A: Railway (Recommended — free tier available)
1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Push this project to a GitHub repo, connect it
3. Add environment variables in Railway dashboard:
   - `SLACK_SIGNING_SECRET`
   - `ANTHROPIC_API_KEY` (if you use **anthropic** mode)
   - Optional: `ADMIN_TOKEN` (required to change engine via the `/` page when set), `ENGINE_DEFAULT` (`hash` or `anthropic`)
4. Railway auto-detects the `Procfile` and deploys
5. Copy the generated URL (e.g. `https://grandmastagenreselecta.up.railway.app`)
6. Update your Slack slash command Request URL to `https://YOUR-RAILWAY-URL/grandmastagenreselecta`

#### Option B: Render (Also free tier)
1. Go to [render.com](https://render.com) → New Web Service → Connect GitHub
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Add environment variables in Render dashboard
5. Same URL update step as above

#### Option C: Your own server
```bash
pip install -r requirements.txt
export SLACK_SIGNING_SECRET=...
gunicorn app:app --bind 0.0.0.0:3000
```
Point your Slack slash command at `http://YOUR-SERVER-IP:3000/grandmastagenreselecta`

---

### 4. Final Slack Configuration

Once deployed:
1. Go back to [api.slack.com/apps](https://api.slack.com/apps) → your app → **Slash Commands**
2. Edit `/grandmastagenreselecta` → update Request URL with your live URL
3. Reinstall the app to your workspace if prompted

---

## Engine toggle

After deploy, visit **`https://YOUR-HOST/`** in a browser:

- Choose **hash** or **anthropic** and save (enter **Admin token** if you set `ADMIN_TOKEN` in Railway).
- If `ADMIN_TOKEN` is unset, quick links work without a token (dev only).

**`/status`** JSON shows the active engine. The choice is stored in a small file on the server (`.engine_mode` next to `app.py`, or `ENGINE_MODE_FILE`); it resets if that file is lost on redeploy unless you set `ENGINE_DEFAULT`.

---

## Usage

In any Slack channel your app is invited to:
```
/grandmastagenreselecta 91251A307
```

Just type the SKU from your physical catalog after the command. The bot responds in-channel with:
- The SKU you entered
- The mapped music genre
- “Decode” lines (deterministic hash text, or Claude when that engine is active)
- A button to open **Spotify search** for the mapped genre (then choose Playlists on web or in the app)
- A button to explore the genre on EveryNoise.com

---

## Project Structure

```
GrandMastaGenreSelecta/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── Procfile            # For Railway/Render deployment
├── .env.example        # Environment variable template
└── README.md           # This file
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SLACK_SIGNING_SECRET` | ✅ | From Slack app Basic Information |
| `ANTHROPIC_API_KEY` | For Claude mode | Required when engine is `anthropic` |
| `ENGINE_DEFAULT` | Optional | `hash` or `anthropic` if no `.engine_mode` file |
| `ADMIN_TOKEN` | Optional | If set, required to change engine via `/` |
| `ENGINE_MODE_FILE` | Optional | Override path for engine state file |
| `PORT` | Optional | Defaults to 3000 |
