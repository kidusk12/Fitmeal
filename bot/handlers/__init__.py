from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from . import start


def register(app: Application) -> None:
    app.add_handler(CommandHandler("start", start.start))
    app.add_handler(CommandHandler("whoami", start.whoami))
    app.add_handler(CommandHandler("customer", start.customer_preview))
    app.add_handler(CallbackQueryHandler(start.on_callback, pattern=r"^(home|c:home|c:menu|soon:\d+)$"))
