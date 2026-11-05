# Running FitMeal for real

The bot talks to Telegram by polling, so it needs no public address, only an internet connection.
Two things must be running whenever customers might order: the **bot process** and the **PostgreSQL database**.
The bot token can only be used by **one** copy of the bot at a time. If you start a second copy anywhere, both
will show a "Conflict" error. Always stop the old one first.

## Path A: your own Windows PC (fine for a trial day)

It works as long as the PC is on, awake, and online for the whole opening time. A power cut, sleep mode, a closed
laptop or a dropped connection all mean the bot is down.

1. In Windows power settings, set sleep to "Never" while plugged in.
2. Start the bot so that it restarts itself if it ever crashes:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\Users\toroc\OneDrive\Desktop\Code\FitMeal\Fitmeal\scripts\start-bot.ps1
   ```
   Press Ctrl+C to stop it.
3. Optional, start it automatically when you sign in to Windows:
   ```powershell
   $project = "C:\Users\toroc\OneDrive\Desktop\Code\FitMeal\Fitmeal"
   $action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$project\scripts\start-bot.ps1`""
   $trigger = New-ScheduledTaskTrigger -AtLogOn
   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
   Register-ScheduledTask -TaskName "FitMealBot" -Action $action -Trigger $trigger -Settings $settings
   ```
   To remove it later: `Unregister-ScheduledTask -TaskName FitMealBot -Confirm:$false`
4. Your project folder is inside OneDrive. That means `.env` (bot token) and `backups\` (customer names, phones and
   addresses) are copied to OneDrive. If you don't want that, set `BACKUP_DIR` in `.env` to a folder outside OneDrive.

## Path B: in the cloud (better for the real kitchen)

You need a hosted PostgreSQL database and a service that can run a Python program all day. I haven't checked any
provider's current free plans or prices, so compare a few before you choose, and pick a region close to Ethiopia.
A host abroad is not affected by your own home connection dropping.

1. **Create the database** and copy its connection string. It looks like `postgresql://user:pass@host/dbname?sslmode=require`.
2. **Move your data** (stop the bot on your PC first):
   ```powershell
   python -m bot.backup
   python -m bot.restore backups\fitmeal-<the newest file>.sql --url "<the cloud connection string>"
   ```
   The restore creates the tables if the database is empty, then loads everything. It asks you to type YES.
3. **Create the service** from your GitHub repository (the `main` branch):
   - Python 3.11 or newer
   - Build/install command: `pip install -r requirements.txt`
   - Start command: `python -m bot.main`
   - Environment variables: `BOT_TOKEN`, `DATABASE_URL` (the cloud one), `ADMIN_IDS`, `TIMEZONE=Africa/Addis_Ababa`.
     Do not upload your `.env` file. Type these values into the host's settings page.
4. **Check it**: send `/status` to the bot. You should see the database OK and the payment timer running.
5. **Backups on a cloud host**: the host's disk is often wiped when it redeploys, so the `backups` folder may not
   survive. The daily backup is also sent to you on Telegram (`BACKUP_SEND=1`), which gives you a copy that does.
   If your database provider offers its own backups or point-in-time restore, switch that on too.

## Switching from your PC to the cloud

1. `python -m bot.backup`, then try the restore on a scratch database first (see PILOT.md).
2. Stop the bot on your PC. Start the cloud service.
3. `/status`, then place one test order from a customer account and take it all the way to Delivered.
4. Don't start the bot on your PC again unless you stop the cloud one.

## When something goes wrong

| Problem | Do this |
|---|---|
| The bot doesn't answer | Send `/status`. Then look at the host's logs (or `logs\fitmeal.log` on your PC). |
| "Conflict: terminated by other getUpdates request" | A second copy is running somewhere. Stop it. |
| The database is not reachable | Check the database service. Orders already placed are safe; the timers catch up when it returns. |
| Data lost or wrong | Stop the bot, `python -m bot.restore <newest good backup>`, start the bot. |
| The bot token leaked | In BotFather, revoke the token, put the new one in `BOT_TOKEN`, restart. |
