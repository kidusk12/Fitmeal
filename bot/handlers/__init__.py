from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from . import browse, cart, checkout, orders, payment, signup, start


def register(app: Application) -> None:
    # Runs before everything else (group -1) and never blocks anything: when the customer taps
    # a button outside checkout, or sends /start, a half-finished checkout is forgotten.
    app.add_handler(CallbackQueryHandler(checkout.forget, pattern=checkout.LEAVING), group=-1)
    app.add_handler(CommandHandler("start", checkout.forget), group=-1)

    # Conversations first, so they see messages before the plain handlers do.
    # The note conversation comes before signup so that /start can cancel a half-typed note.
    # Checkout comes last among them so that signup and notes always get the text they are waiting for.
    app.add_handler(cart.note_conversation())
    app.add_handler(signup.conversation())
    app.add_handler(checkout.conversation())

    app.add_handler(CommandHandler("whoami", start.whoami))
    app.add_handler(CommandHandler("customer", start.customer_preview))

    app.add_handler(CallbackQueryHandler(start.on_callback, pattern=start.PATTERN))
    app.add_handler(CallbackQueryHandler(browse.on_callback, pattern=browse.PATTERN))
    app.add_handler(CallbackQueryHandler(cart.on_callback, pattern=cart.PATTERN))
    app.add_handler(CallbackQueryHandler(orders.on_callback, pattern=orders.PATTERN))
    app.add_handler(CallbackQueryHandler(checkout.on_callback, pattern=checkout.PATTERN))
    app.add_handler(CallbackQueryHandler(signup.on_profile, pattern=r"^profile$"))
    app.add_handler(CallbackQueryHandler(payment.on_callback, pattern=payment.PATTERN))
    # A photo (or image file) sent to the bot is treated as a payment screenshot.
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, payment.on_screenshot))

    # Payment timers: expiry and kitchen reminders, all driven by database timestamps.
    app.job_queue.run_repeating(payment.tick, interval=payment.TICK_SECONDS, first=5, name="payment_timers")
