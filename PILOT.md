# Pilot day checklist

A pilot is one real day with the real kitchen and a small group of real customers. The aim is to find problems
while they are cheap. Nothing here is about new features.

## A week before

- [ ] Replace every sample item with real data (Meals screen): names, prices, descriptions, recipes, photos, ingredients.
      Every meal needs its ingredients, or the meal builder can't suggest it.
- [ ] Payment accounts: the real Telebirr/bank numbers and holder names. Remove or hide the sample one.
- [ ] Settings: delivery fee, opening and closing time, daily order limit, payment window, kitchen review time.
- [ ] Staff: each kitchen person sends `/whoami` to the bot, you add them under Staff, and they send `/start`.
- [ ] BotFather: set the bot's description, about text, and a command list that contains only `start`.
- [ ] Take a **dress rehearsal** with the kitchen: a customer account orders and sends a screenshot, the kitchen
      approves with a time, moves it through every status, and the customer sees each message. Also test a denial,
      an expired order, a refund, and sold out.
- [ ] Clear the rehearsal orders so reports start clean. Take a backup first, then (this deletes ALL orders, keeps
      customers, meals, settings, accounts and staff):
      ```powershell
      python -m bot.backup
      & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d fitmeal_dev -c "TRUNCATE orders, order_items, payments, order_events, refunds, order_counters, cart_items, broadcasts RESTART IDENTITY CASCADE;"
      ```
      Change the database name if your pilot database is a different one.

## Backup and restore rehearsal (do this once, before the pilot)

```powershell
python -m bot.backup
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE fitmeal_restore_test;"
python -m bot.restore backups\<newest file>.sql --url "postgresql://postgres:YOURPASSWORD@localhost:5432/fitmeal_restore_test"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -d fitmeal_restore_test -c "SELECT count(*) FROM orders;"
```
The count must match your real database. A backup you have never restored is only a hope.

## The day before

- [ ] `/backup`, and check the file arrives.
- [ ] `/status`: database OK, timer running.
- [ ] Decide who watches Telegram all day and who is the backup person. Write down their phone numbers.
- [ ] Tell the customers (Broadcast): opening hours, how to pay, what to do if the bot is slow.
- [ ] Power, internet and phone charge for whoever runs the machine (Path A in DEPLOY.md).

## During the day

- Send `/status` every hour or two. Check the timer is running and "waiting for review" is not growing.
- A payment waiting more than 30 minutes sends an overdue alert and the customer can ask for a refund. Don't let it get there.
- If the bot restarts, you get a "FitMeal started" message with the number of orders waiting. Check those first.
- Write every problem down at once: time, what the customer did, what they saw. Screenshots help.

## If the bot goes down

1. Check the machine is on and online, and look for the error in `logs\fitmeal.log`.
2. Restart it. Nothing is lost: orders, payments and timers all live in the database, and overdue timers catch up
   within about 15 seconds of the bot starting.
3. Customers in the middle of checkout, or typing a note, may have to press /start again. The bot tells them so.
4. While it is down, tell customers directly (phone or social media) that orders are paused.

## After the day

- [ ] Reports: compare the day's totals with the kitchen's own count and the money received.
- [ ] `/backup`.
- [ ] Go through the written problems and sort them: blocks an order, confusing, or nice to have.
- [ ] Ask the kitchen and a few customers what felt slow or unclear.
