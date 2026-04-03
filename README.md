# GrandMastaGenreSelecta

A Slack slash command that takes a McMaster-Carr SKU from your physical catalog, uses Claude AI to creatively map it to a music genre from [EveryNoise.com](https://everynoise.com), and posts the result to your Slack channel — complete with a one-click Spotify link.

**Example output:**
> 🔩 **GrandMastaGenreSelecta** 🎵
> SKU: `91251A307` → Genre: *deep nordic folk*
> SKU Decoded: A high-tensile hex bolt — cold, precise, Scandinavian-engineered.
> Why this genre: Like this bolt, deep nordic folk holds everything together in silence and ice.
> [🎧 Open in Spotify] [🗺️ Explore on EveryNoise]

---

## How It Works

1. You type `/grandmastagenreselecta` followed by a SKU from your physical McMaster-Carr catalog
2. Claude AI decodes the SKU and maps it to a genre on EveryNoise.com
3. A message is posted to your channel with the SKU, genre, Claude's reasoning, and links

---

## Setup

### 1. Get Your API Keys

#### Anthropic (Claude)
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Save it — you'll need it as `ANTHROPIC_API_KEY`

#### Slack App
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
   - `ANTHROPIC_API_KEY`
   - `SLACK_SIGNING_SECRET`
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
export ANTHROPIC_API_KEY=...
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

## Usage

In any Slack channel your app is invited to:
```
/grandmastagenreselecta 91251A307
```

Just type the SKU from your physical catalog after the command. The bot responds in-channel with:
- The SKU you entered
- The mapped music genre
- Claude's creative interpretation of the SKU
- A button to open the genre in Spotify
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
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key |
| `SLACK_SIGNING_SECRET` | ✅ | From Slack app Basic Information |
| `PORT` | Optional | Defaults to 3000 |
