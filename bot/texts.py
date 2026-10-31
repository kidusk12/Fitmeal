"""All customer and staff messages live here so they are easy to edit (or translate later)."""

WELCOME_CUSTOMER = (
    "Welcome to <b>FitMeal</b>! 🥗\n\n"
    "Healthy meals, delivered to your door. Choose an option below."
)
WELCOME_STAFF = (
    "Welcome back to <b>FitMeal</b> 👋\n"
    "You are signed in as <b>{role}</b>."
)
COMING_SOON = "This feature arrives in Phase {phase}."

# ---- signup and profile ----
SIGNUP_INTRO = "Welcome to <b>FitMeal</b>! 🥗\nLet's set up your profile first. It takes about a minute."
SHARE_NUMBER = "📱 Share my number"
ASK_NAME = "What is your <b>full name</b>?"
ASK_PHONE = (
    "What is your <b>phone number</b>?\n"
    "Type it (for example 0911223344) or tap the button below. The kitchen uses it to reach you about deliveries."
)
ASK_ALLERGIES = (
    "Do you have any <b>food allergies</b>?\n"
    "Type them (for example: peanuts, dairy) or tap <b>None</b>."
)
ASK_GOAL = "What is your <b>fitness goal</b>? Tap one or type your own."
ASK_LOCATION = (
    "Which <b>area</b> do you usually order to?\n"
    "For example: Bole, near Edna Mall. You can send an exact location for each order later."
)
ERR_NAME = "Please enter your full name (2 to 80 characters)."
ERR_PHONE = "That doesn't look like an Ethiopian mobile number. Try 0911223344 or +251911223344."
ERR_ALLERGIES = "Please type your allergies, or tap None (up to 200 characters)."
ERR_GOAL = "Please enter your goal in a few words (up to 60 characters)."
ERR_LOCATION = "Please enter an area name (2 to 120 characters)."
SIGNUP_DONE = "You're all set! 🎉"
UPDATE_INTRO = "Let's update your profile. Tap <b>Keep current</b> to leave a field as it is."
CANCELLED = "Cancelled."
PROFILE = (
    "<b>Your profile</b>\n\n"
    "Name: {name}\n"
    "Phone: {phone}\n"
    "Allergies: {allergies}\n"
    "Goal: {goal}\n"
    "Usual area: {location}"
)

# ---- browsing ----
BROWSE_HEADER = "<b>Choose a category</b>"
BROWSE_EMPTY = "The menu is empty right now. Please check back soon."
CATEGORY_HEADER = "<b>{name}</b>\nPick a meal:"
SOLD_OUT = "❌ <b>Sold out today.</b>"
ALLERGY_WARNING = (
    "⚠️ <b>Allergy warning:</b> contains {items}, which may match the allergies in your profile. "
    "Please check with the kitchen before ordering."
)
MEAL_UNAVAILABLE = "Sorry, this meal is not available right now."

# ---- cart ----
CART_EMPTY = "🛒 Your cart is empty."
CART_HEADER = "🛒 <b>Your cart</b>\n"
CART_FOOTER = "\n<b>Subtotal: {subtotal} ETB</b>\n<i>The delivery fee is added at checkout.</i>"
CART_ALLERGY_LEGEND = "\n⚠️ = may match your allergies"
CART_UNAVAILABLE = "   ❌ Not available right now. Please remove it."
CART_FULL = "Your cart can hold up to {n} different meals."
CART_MAX = "You can order up to {n} portions of one meal."
ADDED = "Added to your cart ✅"
ASK_NOTE = (
    "Type a short note for <b>{code} {name}</b> (up to 120 characters), "
    "for example: less spicy.\n<i>Notes are a request, not a guarantee.</i>"
)
NOTE_TOO_LONG = "That note is too long. Please keep it under 120 characters."

# ---- orders ----
ORDERS_EMPTY = "You haven't placed any orders yet."
ORDERS_HEADER = "<b>Your recent orders</b>\n"
STATUS_LABELS = {
    "awaiting_payment": "Awaiting payment",
    "payment_review": "Payment under review",
    "confirmed": "Confirmed",
    "preparing": "Preparing",
    "ready": "Ready",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "expired": "Expired",
    "payment_denied": "Payment denied",
    "cancelled": "Cancelled",
    "refund_needed": "Refund pending",
    "refunded": "Refunded",
}

# ---- checkout (Phase 3) ----
CLOSED = (
    "We're closed right now 🌙\n"
    "Orders are taken from <b>{opens}</b> to <b>{closes}</b> (Addis Ababa time). Please come back then."
)
LIMIT_REACHED = "We've reached today's order limit 🙏 Please try again tomorrow."
CHECKOUT_EMPTY = "Your cart is empty, so there is nothing to order."
CHECKOUT_UNAVAILABLE = "These items are no longer available: {names}. Please remove them from your cart first."
CHECKOUT_EXPIRED = "This checkout timed out. Open your cart and tap Checkout to start again."
PRICE_CHANGED = "⚠️ The total changed while you were checking out. Please review it and confirm again."

CHECKOUT_DEST = (
    "<b>Checkout</b>\n\n{summary}\n\n"
    "<b>Where should we deliver?</b>\n"
    "Send a 📍 location pin (you can pick any place on the map), paste a Google Maps link, "
    "or type an address or landmark. Or choose a saved address below."
)
ERR_MAPS_LINK = (
    "I couldn't find a location in that link. Please send a 📍 pin from Telegram, "
    "paste a Google Maps link that shows a pin, or type the address."
)
ERR_ADDRESS = "Please type an address or landmark (3 to 200 characters), or send a location pin."
ASK_RECEIVER = "<b>Who will receive this order?</b>"
ASK_RECEIVER_NAME = "What is the <b>receiver's name</b>?"
ASK_RECEIVER_PHONE = "What is the <b>receiver's phone number</b>? For example 0911223344."
ASK_ADDRESS_LABEL = "Give this address a short name, for example <b>Home</b> or <b>Office</b> (up to 30 characters)."
ERR_ADDRESS_LABEL = "Please use 1 to 30 characters."
ADDRESS_SAVED = "Address saved ✅"
ADDRESS_LIMIT = "You can save up to {n} addresses."

CONFIRM_HEADER = "<b>Please confirm your order</b>\n"
CONFIRM_FOOTER = "\n<i>After you confirm, you'll get the payment details.</i>"
ORDER_PLACED = (
    "✅ <b>Order placed</b>\n"
    "Order ID: <b>{code}</b>\n\n"
    "{lines}\n\n"
    "Total: <b>{total} ETB</b>\n\n"
    "{payment}"
)
CANCEL_ASK = "Cancel order <b>{code}</b>?"
ORDER_CANCELLED = "Order <b>{code}</b> has been cancelled."
CANNOT_CANCEL = "This order can no longer be cancelled here. Please contact the kitchen."

# ---- payment and tracking (Phase 4) ----
PAYMENT_BLOCK = (
    "💳 <b>Pay {total} ETB</b> to one of these accounts:\n\n{accounts}\n\n"
    "Then send a <b>screenshot of your payment</b> in this chat before <b>{deadline}</b> "
    "({minutes} minutes from now). If we don't receive it in time, the order expires."
)
PAYMENT_NO_ACCOUNTS = "⚠️ Payment details are not set up yet. Please contact the kitchen."
SHOT_NO_ORDER = "I don't see an order waiting for payment. Open <b>My orders</b> to check your orders."
SHOT_ALREADY = "We already have your screenshot and the kitchen is checking it. You'll get a message when it's done."
SHOT_PICK = "Which order is this payment for?"
SHOT_LOST = "Please send the screenshot again."
SHOT_TOO_LATE = "Sorry, that order is no longer waiting for payment."
SHOT_RECEIVED = (
    "✅ Screenshot received for <b>{code}</b>.\n"
    "The kitchen is checking your payment. You'll get a message as soon as it's done."
)
EXPIRED_MSG = (
    "⏰ Order <b>{code}</b> expired because we didn't receive a payment screenshot in time.\n"
    "You can place a new order any time."
)
STAFF_NEW_SHOT = (
    "💳 <b>Payment to review</b>\n"
    "Order <b>{code}</b> · {total} ETB\n"
    "Customer: {name}, {phone}\n"
    "<i>Approve and Deny buttons arrive in Phase 5.</i>"
)
STAFF_REMINDER = (
    "⏳ <b>Payment review waiting</b>\n"
    "Order <b>{code}</b> · {total} ETB\n"
    "Customer: {name}, {phone}\n"
    "Waiting {minutes} min."
)
STAFF_OVERDUE = (
    "🚨 <b>OVERDUE payment review</b>\n"
    "Order <b>{code}</b> · {total} ETB\n"
    "Customer: {name}, {phone}\n"
    "Waiting {minutes} min. Please approve or deny it now."
)
CUSTOMER_OVERDUE = (
    "Your payment review for <b>{code}</b> is taking longer than expected. "
    "We've alerted the kitchen.\n"
    "If you would rather have your money back, tap <b>Request refund</b>."
)
REFUND_REQUESTED = "Refund requested for <b>{code}</b>. The kitchen will send your money back and confirm here."
REFUND_TOO_EARLY = "The review is still within its normal time. Please wait a little."
STAFF_REFUND = (
    "💸 <b>Refund needed</b>\n"
    "Order <b>{code}</b> · {total} ETB\n"
    "Customer: {name}, {phone}\n"
    "Reason: {reason}"
)
CANCEL_ASK_PAID = (
    "Cancel order <b>{code}</b>?\n"
    "You already sent a payment screenshot, so the kitchen will refund you manually."
)
ORDER_CANCELLED_REFUND = "Order <b>{code}</b> has been cancelled. The kitchen will refund your payment and confirm here."
TRACK_HEADER = "📦 <b>Order {code}</b>\n"

REFUND_ALREADY = "A refund is already on its way for this order. The kitchen will send your money back and confirm here."