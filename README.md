# F1 Ticket Monitor

Monitors Ticketmaster for Formula 1 Grand Prix ticket prices and sends notifications to Telegram. Checks prices on a configurable interval and alerts you when new events appear or prices change.

## Features

- Searches Ticketmaster by event name or direct event ID
- Scrapes actual per-seat prices (section, row, price) via headless Chromium
- Groups tickets by GP session: Practice, Qualifying, Sprint, Race
- Supports sprint weekends (different Saturday schedule)
- Tracks price history and detects changes (min/max price drops or increases)
- Sends formatted HTML notifications to Telegram
- Runs in Docker with persistent price history

## Sample Notification

```
🏎 Formula 1 Miami Grand Prix 2026
📍 Hard Rock Stadium, Miami Gardens, FL

🏁 Race — 2026-05-04 14:00
  Start / Finish Grandstand: от $850.00, Row 11
  Turn 1 Grandstand: от $720.00, Row 5

⚡ Sprint + Qualifying — 2026-05-03 12:00
  Start / Finish Grandstand: от $390.00, Row 8

🔧 Practice — 2026-05-02 10:00
  Start / Finish Grandstand: от $130.00, Row 11

🔗 Buy tickets
```

## Prerequisites

- Python 3.12+
- [Ticketmaster API key](https://developer.ticketmaster.com/) (Consumer Key from your app)
- [Telegram bot token](https://t.me/BotFather) and chat ID

## Quick Start

1. **Clone and install dependencies**

   ```bash
   git clone <repo-url> && cd ticketmaster-f1
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```

2. **Configure secrets**

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:

   ```
   TICKETMASTER_API_KEY=your_consumer_key
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=your_chat_id
   CHECK_INTERVAL_SECONDS=3600
   LOG_LEVEL=INFO
   ```

   To get your Telegram chat ID: send any message to your bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id`.

3. **Configure events**

   Edit `config.yaml`:

   ```yaml
   check_interval_seconds: 3600   # fallback if not set in .env
   timezone: "America/New_York"
   language: "ru"                  # "ru" or "en"

   events:
     - name: "Formula 1 Miami 2026"
       sprint: true

     - name: "Grand Prix Las Vegas"
       sprint: false

     # Or use a direct event ID:
     - event_id: "vvG1zZ9V8h8vKs"
       label: "F1 Miami 2026"
   ```

   | Field | Description |
   |-------|-------------|
   | `event_id` | Ticketmaster event ID (direct lookup, no search) |
   | `name` | Search query for Ticketmaster Discovery API |
   | `label` | Display name (optional, for startup message) |
   | `sprint` | `true` for sprint weekends (Sat = Sprint + Qualifying) |

4. **Run**

   ```bash
   python -m src.monitor
   ```

## Docker

```bash
docker-compose up --build -d
```

Data is persisted in `./data/price_history.json` via a volume mount. The container restarts automatically unless explicitly stopped.

To view logs:

```bash
docker-compose logs -f
```

## Project Structure

```
ticketmaster-f1/
├── config.yaml           # Events to monitor, language, timezone
├── .env                  # Secrets (API keys, tokens, interval)
├── requirements.txt      # httpx, pyyaml, python-dotenv, playwright
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── config.py         # Loads config.yaml + .env, validates
│   ├── ticketmaster.py   # Ticketmaster Discovery API v2 client
│   ├── scraper.py        # Playwright-based price scraper
│   ├── f1_utils.py       # F1 event name parsing, session mapping
│   ├── telegram_bot.py   # Telegram Bot API notifications
│   ├── price_tracker.py  # Price history tracking + change detection
│   └── monitor.py        # Main loop, orchestration
└── data/
    └── price_history.json  # Created at runtime
```

## How It Works

1. **Resolve events** — searches Ticketmaster Discovery API by name or fetches by ID
2. **Parse event names** — extracts day (Fri/Sat/Sun), grandstand section, and GP name from Ticketmaster naming conventions like `"Friday - Start / Finish Grandstand - 2026 Miami Grand Prix"`
3. **Map to sessions** — Friday = Practice, Saturday = Qualifying (or Sprint+Qualifying), Sunday = Race
4. **Scrape prices** — loads each event page in headless Chromium to get per-seat prices (section, row, price) since the free API only returns price ranges
5. **Track changes** — compares current prices against history, detects new events and price movements
6. **Notify** — sends a consolidated message per Grand Prix to Telegram, grouped by session type

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TICKETMASTER_API_KEY` | Yes | — | Consumer Key from developer.ticketmaster.com |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | — | Your Telegram chat ID |
| `CHECK_INTERVAL_SECONDS` | No | `3600` | How often to check prices (seconds) |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## License

MIT
