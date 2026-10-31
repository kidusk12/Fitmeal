from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from . import browse, cart, orders, signup, start


def register(app: Application) -> None:
    # Conversations first, so they see messages before the plain handlers do.
    # The note conversation comes before signup so that /start can cancel a half-typed note.
    app.add_handler(cart.note_conversation())
    app.add_handler(signup.conversation())

    app.add_handler(CommandHandler("whoami", start.whoami))
    app.add_handler(CommandHandler("customer", start.customer_preview))

    app.add_handler(CallbackQueryHandler(start.on_callback, pattern=start.PATTERN))
    app.add_handler(CallbackQueryHandler(browse.on_callback, pattern=browse.PATTERN))
    app.add_handler(CallbackQueryHandler(cart.on_callback, pattern=cart.PATTERN))
    app.add_handler(CallbackQueryHandler(orders.on_callback, pattern=orders.PATTERN))
    app.add_handler(CallbackQueryHandler(signup.on_profile, pattern=r"^profile$"))
