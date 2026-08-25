# StockChecker 2

StockChecker is a Discord bot that monitors Disney Store product pages and sends direct
messages when availability or price changes. It is designed for Python 3.12 and AMP's
Python App Runner on x86-64 Ubuntu.

The modern application lives in `stockchecker/`. Older top-level modules remain only as
historical reference and are not imported by `main.py`.

## Discord commands

- `/subscribe url:<supported product URL> max_price:<optional USD price>`
- `/unsubscribe url:<product URL>`
- `/subscriptions`
- `/status`

Command responses are private. Stock-change notifications are delivered by DM, so users
must allow direct messages from the bot/server.

## Local setup

1. Install Python 3.12.
2. Create and activate a virtual environment.
3. Install `requirements.txt`.
4. Copy `.env.example` to `.env` and fill in the values.
5. Enable the bot scopes `bot` and `applications.commands` when inviting the application.
6. Run `python main.py`.

During development, set `DISCORD_GUILD_ID` to your test server ID so slash-command changes
appear immediately. For global commands, leave it blank; Discord can take time to publish
global command changes.

## AMP Python App Runner

Create a separate **Python App Runner** instance (not Node.js App Runner):

- Download type: Git repository
- Package install method: `requirements.txt`
- Run mode: Python script
- Script/module name: `main.py`
- Python: 3.12

Set the environment values from `.env.example` in AMP. Point `DB_PATH` at a persistent
folder in the AMP instance, such as `./data/stockchecker.db`. No inbound port is needed.

## Safety and behavior

- The minimum polling interval is 60 seconds; 180 seconds is the default.
- Network errors, rate limits, and unrecognized pages are logged as check failures and are
  never interpreted as out of stock.
- The latest 500 observations per product are retained.
- SQLite uses WAL mode and contains no Discord token.
- Do not commit `.env`, the database, or your Discord token.

Disney may change its storefront markup. Run the included parser tests and perform a manual
subscription check after deploying. If Disney stops publishing structured product data, the
Disney checker will fail safely and will need its parser updated.
