import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    role = "owner" if uid in ADMIN_IDS else "customer"
    await update.message.reply_text(f"FitMeal is alive. Your ID: {uid}. Role: {role}.")

if not TOKEN:
    raise SystemExit("BOT_TOKEN is missing in .env")
app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .pool_timeout(30)
    .get_updates_connect_timeout(30)
    .get_updates_read_timeout(40)
    .build()
)
app.add_handler(CommandHandler("start", start))
app.run_polling()