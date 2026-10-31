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
