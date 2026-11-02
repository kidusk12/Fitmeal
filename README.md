# FitMeal

Telegram bot for ordering healthy meals for delivery, with manual payment verification by the kitchen.
Requirements: see the SRS document. Status: **Phase 5 (kitchen console)**: ordering, payment by screenshot, kitchen approval, status tracking, refunds.

## Setup (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env with your real values
```

Create a local database once (use pgAdmin or psql):

```powershell
psql -U postgres -c "CREATE DATABASE fitmeal_dev;"
```

Create the tables and load the sample data, then start the bot:

```powershell
python -m bot.setup_db
python -m bot.main
```

## Layout

- `schema.sql`, `seed.sql`: database tables and sample data (edit the sample prices, recipes and payment account)
- `bot/config.py`: reads `.env`
- `bot/db.py`: PostgreSQL connection pool
- `bot/auth.py`: owner / kitchen / customer roles
- `bot/texts.py`: every message the bot sends
- `bot/handlers/`: one file per feature area (start, signup, browse, cart, orders)
- `bot/services/`: logic without Telegram code (cart, users, phone, allergy matching)
- `bot/handlers/kitchen.py`, `bot/services/kitchen.py`, `bot/services/flow.py`: the kitchen console (dashboard, approve/deny, statuses, recipes, refunds, sold out)
- `tests/`: run with `python -m unittest discover -s tests -v`
- `legacy/Fitmeal.py`: the original 2-year-old bot, kept for reference only

Never commit `.env`. It holds the bot token and database password.
