# Student of the Week Bot

A Discord bot that runs a hands-off weekly "Student of the Week" feature for an NMS
server community. Members submit their work, the bot screens and scores the entries,
staff get a 12-hour window to veto the pick, and the winner is announced and published
to a small file and web endpoint that the game server can read.

This is a standalone service. It does not modify the server, the database or the client.

**Status:** unit-tested (21 tests). Not yet run against a live Discord server, a real AI
endpoint or the game client. Do the dry run in step 11 before announcing it.

## How it works

1. Members run `/submit` with a title, a link and a short description.
2. Every Sunday at 8 pm (server time zone is configurable) the bot screens the entries,
   scores them with an AI model plus thumbs-up reactions, and picks one.
3. The pick is posted in a private staff channel and goes live 12 hours later. Staff can
   run `/sotw_veto` to stop it (the runner-up is then picked). If nobody acts, it publishes.
4. The bot announces the winner, archives it, and writes `data/winner.json`,
   `data/winner.txt` and serves `/winner.json`, `/winner.txt` and `/student`
   (a redirect to the winner's link).

If anything fails (no entries, AI error, paused), the current winner stays and nothing
partial is published. `/sotw_revert` is a kill switch that clears the winner and pauses
the bot.

## What you need

- A Discord server where you can manage the server (to add a bot and create channels)
- A machine to run the bot: Windows, Linux or macOS with **Python 3.11 or newer**
- About 15 minutes

An AI key is optional. Without one, the bot ranks entries by thumbs-up reactions only and
sends no data to any outside service.

---

## Step-by-step setup

### Step 1. Create the Discord application and bot

1. Open <https://discord.com/developers/applications> and click **New Application**.
   Name it (for example "Student of the Week").
2. Open **Bot** in the left menu. Click **Reset Token**, then **Copy**. Keep this token
   private. Anyone with it controls the bot. You will paste it into `.env` in step 5.
3. Still on **Bot**, scroll to **Privileged Gateway Intents** and turn on
   **Server Members Intent**. The bot needs it to check how long a member has been in
   the server. **Message Content Intent is not needed**; leave it off.

### Step 2. Invite the bot to your server

1. Open **OAuth2 > URL Generator**.
2. Under **Scopes** tick `bot` and `applications.commands`.
3. Under **Bot Permissions** tick only these five:
   - View Channels
   - Send Messages
   - Embed Links
   - Add Reactions
   - Read Message History
4. Copy the generated URL, open it in your browser, choose your server and authorize.

The bot never needs Administrator, Manage Messages, Kick or Ban.

### Step 3. Create the channels

Create these text channels (the names are up to you):

| Channel | Who can see it | Purpose |
|---------|----------------|---------|
| #sotw-submissions | Everyone | The bot posts each entry here. Members react with a thumbs up. |
| #sotw-staff | Staff only | Pick notices (with the veto window) and error messages |
| #sotw-announcements | Everyone (read only) | The weekly winner announcement |
| #sotw-hall-of-fame | Everyone (read only), optional | Archive of past winners |

Give the bot's role **View Channel**, **Send Messages**, **Embed Links**,
**Add Reactions** and **Read Message History** on these channels.

### Step 4. Collect the IDs

1. In Discord, open **User Settings > Advanced** and turn on **Developer Mode**.
2. Right-click your server name and choose **Copy Server ID**. This is `GUILD_ID`.
3. Right-click each channel and choose **Copy Channel ID** for the four channels above.

### Step 5. Install the bot

Copy this folder to the machine that will run it, then open a terminal in it.

**Windows (PowerShell):**

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

**Linux / macOS:**

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

### Step 6. Fill in `.env`

Open `.env` in a text editor and set at least these. Every other setting has a working
default; the comments in `.env.example` explain each one.

| Setting | Value |
|---------|-------|
| `DISCORD_TOKEN` | The token from step 1 |
| `GUILD_ID` | Server ID from step 4 |
| `SUBMIT_CHANNEL_ID` | #sotw-submissions ID |
| `STAFF_CHANNEL_ID` | #sotw-staff ID |
| `ANNOUNCE_CHANNEL_ID` | #sotw-announcements ID |
| `HALL_CHANNEL_ID` | #sotw-hall-of-fame ID (leave empty to skip) |
| `TIMEZONE` | Your time zone, for example `America/New_York` |
| `BLOCKED_WORDS` | Comma-separated words your community does not allow |

Do not commit `.env` or share it. It is already in `.gitignore`.

### Step 7. Start the bot

```
.venv\Scripts\python -m sotw          (Linux/macOS: .venv/bin/python -m sotw)
```

You should see log lines ending without errors, and within a few seconds the slash
commands (`/submit`, `/student`, and so on) appear in your server. If they do not,
wait a minute and re-open Discord, and check that the invite included
`applications.commands` (step 2).

Stop it with Ctrl+C.

### Step 8. (Optional) Turn on AI scoring

In `.env`:

```
AI_API_KEY=your key
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o-mini
```

Any OpenAI-compatible chat completions endpoint works. What is sent: each entry's
title, description and the site name of its link. No Discord names, IDs or messages are
sent. Entries are passed as data with an instruction to ignore any instructions inside
them, and the reply must be valid scores (0 to 10) or the cycle fails safe and keeps the
current winner.

Optional: set `MODERATION_URL` to an OpenAI-style moderation endpoint
(`https://api.openai.com/v1/moderations`) to reject flagged entries at submission.
If that endpoint is set and fails, entries are rejected rather than accepted unchecked.

### Step 9. Run it as a service so it survives reboots

**Windows:** use [NSSM](https://nssm.cc/) or Task Scheduler. With Task Scheduler: create
a task that runs at startup, program `C:\path\to\.venv\Scripts\python.exe`, arguments
`-m sotw`, start in the bot folder, and tick "Run whether user is logged on or not".

**Linux (systemd):** create `/etc/systemd/system/sotw-bot.service`:

```
[Unit]
Description=Student of the Week bot
After=network-online.target

[Service]
WorkingDirectory=/opt/student-of-the-week-bot
ExecStart=/opt/student-of-the-week-bot/.venv/bin/python -m sotw
Restart=on-failure
User=sotw

[Install]
WantedBy=multi-user.target
```

Then `sudo systemctl enable --now sotw-bot`. Use a dedicated low-privilege user.

Back up the `data/` folder (it holds `sotw.sqlite`).

### Step 10. Check the web endpoint

The bot serves a small read-only endpoint on `HTTP_HOST:HTTP_PORT`
(default `127.0.0.1:8765`):

```
curl http://127.0.0.1:8765/healthz        -> ok
curl http://127.0.0.1:8765/winner.json    -> current winner (active: false when none)
curl http://127.0.0.1:8765/winner.txt     -> "Title by Author"
http://127.0.0.1:8765/student             -> redirects to the winner's link
```

It binds to localhost by default. If the game server is on another machine, either put a
reverse proxy in front of it, or set `HTTP_HOST=0.0.0.0` behind a firewall that only
allows the game server. Set `PUBLIC_BASE_URL` to the address players or the server will
use, since it is written into `winner.json` as `short_url`.

### Step 11. Do a dry run before announcing

1. In `.env`, temporarily set `VETO_HOURS=0` so a pick publishes immediately, and set
   `SUBMIT_CHANNEL_ID`, `STAFF_CHANNEL_ID` and `ANNOUNCE_CHANNEL_ID` to test channels
   (or keep them and warn members). Also set `MIN_ACCOUNT_AGE_DAYS=0` and
   `MIN_MEMBER_DAYS=0` if you are testing with a new account. Restart the bot.
2. Run `/submit` with a title, an allowed link (a YouTube or Discord link) and a short
   description. Check that the entry appears in #sotw-submissions and that `/mysubmissions`
   lists it.
3. Run `/sotw_run` (needs Manage Server). Check the staff channel notice, the
   announcement, and `data/winner.txt`.
4. Run `/student`, then `/sotw_status`, then `/sotw_revert` to confirm the kill switch
   clears the winner. Run `/sotw_resume` afterwards.
5. Put the settings back (`VETO_HOURS=12` and your real limits and channels) and restart.

### Step 12. (Optional) Show the winner in game

The bot does not change the game client. The in-game Marketplace banner and
"Item Of The Week" panel are client UI, so they do not read from the bot on their own.
Showing the winner there needs a client-side change (a UI file and a way to push text to
the client, as the client DLL does for the pet list), which is outside this folder.

A simple server-side option that needs no client change is in
[`ingame/student_of_the_week.lua`](ingame/student_of_the_week.lua). It tells each player
the current winner when they connect, by reading `winner.txt`. Its header explains the
two-line install into `quests/global/global_player.lua`. **It is untested.** It assumes
the bot's `data/winner.txt` is readable from the machine running the zone servers
(same machine, or a synced copy), and that the Lua `io` library is available to quest
scripts. Test it on a development server first.

---

## Commands

| Command | Who | What it does |
|---------|-----|--------------|
| `/submit` | Everyone | Submit a title, link and description |
| `/mysubmissions` | Everyone | List your entries for the week |
| `/withdraw` | Everyone | Withdraw one of your entries |
| `/student` | Everyone | Show the current winner and link |
| `/sotw_optout` | Everyone | Never be featured; removes your current entries |
| `/sotw_optin` | Everyone | Allow being featured again |
| `/sotw_status` | Manage Server | Show live and pending picks and pause state |
| `/sotw_run` | Manage Server | Run the weekly cycle now |
| `/sotw_veto` | Manage Server | Cancel the pending pick and promote the runner-up |
| `/sotw_revert` | Manage Server | Kill switch: clear the winner and pause the bot |
| `/sotw_resume` | Manage Server | Resume after a pause |

Staff commands are hidden from members by default and also check the Manage Server
permission when run.

## Safety and privacy

- **Veto window:** a pick waits `VETO_HOURS` (default 12) before going live.
- **Link allowlist:** only the sites in `LINK_HOSTS` are accepted. No embedded
  credentials and no schemes other than http and https.
- **Filtering:** `BLOCKED_WORDS` (including simple look-alike spellings), mention
  stripping, control-character removal, and the optional moderation check.
- **Limits:** account age (14 days), time in server (3 days), 2 entries per week,
  duplicate links rejected.
- **Client-safe text:** titles and names published for the game have markup, links and
  special characters removed and are length-limited.
- **No pings:** the bot's messages never mention anyone.
- **Data stored:** entries (title, link, description, display name, user ID), scores,
  picks and opt-outs in `data/sotw.sqlite`. `/sotw_optout` removes a member's current
  entries.
- **Secrets:** `.env` holds the Discord token and the AI key. Rotate the token if it is
  ever exposed.
- **Web endpoint:** read-only, returns only the current winner's public details.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Set DISCORD_TOKEN and GUILD_ID" on start | `.env` is missing or not filled in (step 6) |
| `PrivilegedIntentsRequired` error | Turn on Server Members Intent (step 1) |
| Slash commands do not appear | Re-invite with `applications.commands` (step 2); check `GUILD_ID` |
| Bot cannot post | Give its role access to the channels (step 3) |
| Entries rejected: site not allowed | Add the site to `LINK_HOSTS` |
| `/sotw_run` says no entries | Entries must be from this ISO week; check `/mysubmissions` |
| Cycle says scoring failed | Check the AI key, URL and model, or clear `AI_API_KEY` to use reactions only |
| Port already in use | Change `HTTP_PORT` |

## Tests

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

21 tests cover screening, scheduling, the veto window, the kill switch, tie-breaks,
opt-outs, failure handling and the web endpoint.

## Files

```
sotw/            bot code (bot.py: Discord, engine.py: weekly cycle, screening.py,
                 ai.py, db.py, publisher.py: files + web endpoint, config.py)
tests/           unit tests
ingame/          optional, untested server-side Lua message
assets/          banner mockup (SVG), for the client UI team
.env.example     all settings, documented
```

## License

MIT, see [`LICENSE`](LICENSE).
