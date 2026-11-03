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
# ---- kitchen console (Phase 5) ----
STAFF_ONLY = "This is for kitchen staff only."
ALREADY_HANDLED = "Someone already handled this order. Showing its current state."
STAFF_SHOT_CAPTION = "💳 <b>Payment to review</b>\nOrder <b>{code}</b> · {total} ETB\nCustomer: {name}"
STAFF_CANCEL_BTN = "✖️ Cancel"
DASH_HEADER = "📋 <b>Kitchen dashboard</b>\n"
DASH_BODY = (
    "💳 Payment review: <b>{review}</b>\n"
    "🚨 Overdue: <b>{overdue}</b>\n"
    "🍳 To cook: <b>{cook}</b>\n"
    "🛵 Out for delivery: <b>{delivery}</b>\n"
    "💸 Refunds to send: <b>{refunds}</b>"
)
QUEUE_TITLES = {
    "review": "💳 Payment review",
    "overdue": "🚨 Overdue payment reviews",
    "cook": "🍳 To cook",
    "delivery": "🛵 Out for delivery",
    "refunds": "💸 Refunds to send",
}
QUEUE_EMPTY = "Nothing here right now ✅"
CARD_OVERDUE = "🚨 <b>OVERDUE</b>: the customer has waited {minutes} min"
CUSTOMER_UNREACHED = "⚠️ I could not message the customer (they may have blocked the bot). Please call {phone}."
NO_SCREENSHOT = "There is no payment screenshot for this order."
NO_RECIPE = "(no recipe saved yet)"
RECIPE_HEADER = "📖 <b>Recipes for {code}</b>\n"
ASK_APPROVE_TIME = "When will <b>{code}</b> be delivered? Pick a time, or type one. The customer sees it right away."
ASK_TYPED_TIME = "Type the delivery time as HH:MM (24-hour, Addis Ababa time), for example 17:30."
ERR_TIME = "I couldn't read that, or the time has already passed. Use HH:MM, for example 17:30."
ASK_DENY_REASON = "Why is this payment being denied? Type a short reason. The customer will read it."
ASK_RESEND = "Should the customer be allowed to send a new screenshot?"
ASK_CANCEL_REASON = "Why can't this order be delivered? Type a short reason. The customer will read it, and a refund will be needed."
ERR_REASON = "Please type a reason of 3 to 200 characters."
ASK_REFUND_METHOD = "How did you send the money back?"
ASK_REFUND_REF = "Type the transaction ID or a short note, or send - to skip."
KITCHEN_CANCELLED = "Cancelled."
MEALS_HEADER = "🍲 <b>Sold out today</b>\nTap a meal to mark it sold out for today, or put it back on sale."

CUST_APPROVED = (
    "✅ <b>Payment confirmed</b> for order <b>{code}</b>.\n"
    "🕒 Delivery time: about <b>{time}</b>\n"
    "Status: Confirmed"
)
CUST_DENIED = "❌ We couldn't confirm your payment for order <b>{code}</b>.\nReason: {reason}\n\n{next_step}"
DENIED_RESEND = "You can send a new screenshot here now."
DENIED_FINAL = "If you think this is a mistake, please contact the kitchen."
CUST_STATUS = {
    "preparing": "👨‍🍳 Your order <b>{code}</b> is being prepared.",
    "ready": "✅ Your order <b>{code}</b> is ready and waiting for the rider.",
    "out_for_delivery": "🛵 Your order <b>{code}</b> is on its way!",
    "delivered": "📦 Your order <b>{code}</b> was delivered. Enjoy your meal! 🥗",
}
CUST_KITCHEN_CANCELLED = (
    "❌ Order <b>{code}</b> was cancelled by the kitchen.\n"
    "Reason: {reason}\n"
    "We will refund <b>{total} ETB</b> and confirm here."
)
CUST_REFUNDED = "💸 Refund sent for order <b>{code}</b>: <b>{total} ETB</b> via {method}{reference}."
SHOT_PLEASE_PHOTO = "Please send a <b>screenshot (photo)</b> of your payment for {codes}."

# ---- owner tools (Phase 6) ----
OWNER_ONLY = "This is for the owner only."
OWNER_CANCEL_BTN = "✖️ Cancel"
OWNER_CANCELLED = "Cancelled. Nothing was changed."
OWNER_STALE = "That step is no longer active. Open it again from the menu."
OWNER_USE_BUTTONS = "Please tap one of the buttons above, or Cancel."
OWNER_USE_TEXT = "Please type your answer as text, or tap Cancel."
OWNER_MENU_BTN = "⬅️ Menu"
ERR_PHOTO_FILE = "Please send it as a normal <b>photo</b> (not as a file)."

SETTINGS_SCREEN = (
    "⚙️ <b>Settings</b>\n\n"
    "🚚 Delivery fee: <b>{fee} ETB</b>\n"
    "📦 Daily order limit: <b>{limit}</b> orders\n"
    "🕗 Opening hours: <b>{opens} to {closes}</b>\n"
    "⏱ Customer payment window: <b>{window} min</b>\n"
    "🔎 Kitchen review window: <b>{review} min</b>\n"
    "🔔 Overdue alert repeat: <b>{repeat} min</b>\n\n"
    "<i>Changes apply right away. Orders already placed keep the payment deadline they were given.</i>"
)
ASK_SETTING = "New value for <b>{label}</b>: type {hint}.\nCurrent value: <b>{current}</b>"
ERR_SETTING = "That value doesn't work. Please type {hint}."
SETTING_SAVED = "✅ <b>{label}</b> is now <b>{value}</b>."

STAFF_SCREEN = (
    "👥 <b>Staff</b>\n\n{people}\n\n"
    "<i>Owners are set in the ADMIN_IDS line of the .env file. Kitchen staff are managed here.</i>"
)
STAFF_NONE = "No kitchen staff yet."
ASK_STAFF_ID = (
    "Type the new staff member's <b>Telegram ID</b> (numbers only).\n"
    "They can get it by sending /whoami to this bot. They should also open the bot with /start so alerts can reach them."
)
ERR_STAFF_ID = "That doesn't look like a Telegram ID. Please type numbers only, for example 123456789."
ASK_STAFF_NAME = "What name should I show for this person? (2 to 60 characters)"
ERR_PERSON_NAME = "Please type 2 to 60 characters."
STAFF_ADDED = "✅ <b>{name}</b> was added as kitchen staff."
STAFF_REACTIVATED = "✅ <b>{name}</b> is kitchen staff again."
STAFF_EXISTS = "That person is already on the staff list."
STAFF_IS_OWNER = "That ID belongs to an owner. Owners cannot be changed here."
STAFF_WELCOME = "👋 You were added to the <b>FitMeal</b> kitchen team. Send /start to open the kitchen menu."
STAFF_NOT_NOTIFIED = "⚠️ I couldn't message them. They need to open the bot and press /start first."
STAFF_REMOVE_ASK = "Remove <b>{name}</b> from the kitchen team? They will stop getting alerts and lose access to the kitchen tools."
STAFF_REMOVED = "✅ <b>{name}</b> was removed."
STAFF_REMOVE_FAILED = "That person is not active kitchen staff, so nothing changed."

ACCOUNTS_SCREEN = "💳 <b>Payment accounts</b>\nCustomers see the visible accounts when they pay.\n\n{accounts}"
ACCOUNTS_NONE = "No accounts yet."
ACCOUNT_VIEW = "💳 <b>{label}</b>\nNumber: <code>{number}</code>\nHolder: {holder}\nStatus: {status}"
ASK_ACCT_LABEL = "What is the account called? For example <b>Telebirr</b> or <b>CBE</b>. (1 to 30 characters)"
ASK_ACCT_NUMBER = "Type the <b>account number or phone number</b> customers will pay to. (3 to 40 characters)"
ASK_ACCT_HOLDER = "Type the <b>account holder's name</b> exactly as the bank or Telebirr shows it. (2 to 60 characters)"
ASK_ACCT_VALUE = "Type the new <b>{what}</b>. Current: {current}"
ERR_ACCT_LABEL = "Please type 1 to 30 characters."
ERR_ACCT_NUMBER = "Please type 3 to 40 characters."
ACCT_SAVED = "✅ Payment account saved."
ACCT_LAST = "At least one payment account must stay visible, or customers can't pay. Add another one first."
ACCT_DELETE_ASK = "Delete the account <b>{label}</b> for good?"
ACCT_DELETED = "✅ Account deleted."
ACCT_GONE = "That account no longer exists."

MEALS_SCREEN = "🍽 <b>Meals</b> ({total})\nTap a meal to edit it. Codes are made automatically."
MEAL_VIEW = (
    "🍽 <b>{code}</b> {name}\n"
    "Category: {category} · Price: <b>{price} ETB</b>\n"
    "{calories} kcal · Protein {protein} g · Carbs {carbs} g · Fat {fat} g\n"
    "Status: {status}\n"
    "Photo: {photo}\n\n"
    "<b>Ingredients</b>\n{ingredients}\n\n"
    "<b>Description</b>\n{description}\n\n"
    "<b>Recipe</b> (kitchen only)\n{recipe}"
)
MEAL_STATUS_ON = "✅ On sale"
MEAL_STATUS_HIDDEN = "🙈 Hidden from customers"
MEAL_STATUS_SOLD_OUT = "❌ Sold out today"
MEAL_EMPTY_FIELD = "(empty)"
MEAL_GONE = "That meal no longer exists."
ASK_MEAL_NAME = "What is the <b>meal's name</b>? (2 to 60 characters)"
ASK_MEAL_CATEGORY = "Pick the <b>category</b>:"
ASK_NEW_CATEGORY = "Type the name of the new category. (2 to 40 characters)"
ERR_CATEGORY = "Please type 2 to 40 characters."
ASK_MEAL_PRICE = "What is the <b>price</b> in ETB? Whole number, for example 180."
ERR_MEAL_PRICE = "Please type the price as a whole number from 1 to 100000."
ASK_MEAL_MACROS = (
    "Type the <b>calories, protein, carbs and fat</b> in this order, separated by spaces.\n"
    "Example: <code>420 28 55 10</code> means 420 kcal, 28 g protein, 55 g carbs, 10 g fat."
)
ERR_MEAL_MACROS = "I need four numbers: calories, protein, carbs, fat. For example 420 28 55 10."
ASK_MEAL_DESCRIPTION = "Type a short <b>description</b> customers will read (up to 300 characters), or send - to leave it empty."
ASK_MEAL_RECIPE = "Type the <b>recipe</b>. Only the kitchen sees it (up to 1000 characters). Send - to leave it empty."
ERR_MEAL_DESCRIPTION = "Please type up to 300 characters, or send -."
ERR_MEAL_RECIPE = "Please type up to 1000 characters, or send -."
ASK_MEAL_PHOTO = "Send a <b>photo</b> of the meal."
SKIP_PHOTO_BTN = "⏭ Skip photo"
REMOVE_PHOTO_BTN = "🗑 Remove photo"
ASK_MEAL_INGREDIENTS = (
    "Type the <b>ingredients with amounts</b>, separated by commas.\n"
    "Example: <code>Chicken breast 150, Brown rice 150, Olive oil 5ml, Egg 2</code>\n"
    "Amounts are grams unless you add ml or pcs. This list replaces the old one."
)
ERR_ING = {
    "empty": "Please type at least one ingredient with an amount.",
    "format": "Each ingredient needs a name and an amount, like <code>Rice 150</code>. Please try again.",
    "qty": "An amount is out of range. Use a number above 0.",
    "name": "An ingredient name must be 2 to 40 characters and contain letters.",
    "dup": "An ingredient appears twice. Please list each one once.",
    "toomany": "That's too many ingredients (20 at most).",
}
ASK_ALLERGEN = (
    "New ingredient: <b>{name}</b>\n"
    "Does it contain one of these common allergens? This powers the allergy warning customers see."
)
MEAL_CONFIRM = (
    "Please check the new meal:\n\n"
    "<b>{name}</b> · {category} · <b>{price} ETB</b>\n"
    "{calories} kcal · Protein {protein} g · Carbs {carbs} g · Fat {fat} g\n"
    "Ingredients: {ingredients}\n"
    "Photo: {photo}\n"
    "Description: {description}\n"
    "Recipe: {recipe}\n\n"
    "A meal code is assigned when you save."
)
MEAL_ADDED = "✅ Added <b>{code}</b> {name}."
MEAL_UPDATED = "✅ Meal updated. Customers see the change right away."
MEAL_TOGGLED_HIDDEN = "🙈 The meal is now hidden from customers."
MEAL_TOGGLED_SHOWN = "✅ The meal is on sale again."

BC_ASK = (
    "📣 <b>Broadcast</b>\n"
    "Send the message customers should get: plain text, or a photo with a caption (up to 1000 characters).\n"
    "<i>It is sent as plain text, without formatting.</i>"
)
ERR_BC_CONTENT = "Please send text or a photo, up to 1000 characters."
BC_AUDIENCE = "Who should get it?"
BC_ASK_PHONES = "Type the customers' phone numbers, separated by commas or new lines."
ERR_BC_PHONES = "None of those numbers belong to a registered customer. Please check them and try again."
BC_PHONES_MISSING = "⚠️ Not found: {numbers}"
BC_CONFIRM = "This is how it will look. Send it to <b>{count}</b> customer(s)?"
BC_EMPTY = "Nobody is in that group yet."
BC_SENDING = "📣 Sending to {count} customer(s)... I'll tell you when it's done."
BC_DONE = "📣 Broadcast finished: delivered to <b>{delivered}</b> of {total}.{failed}"
BC_FAILED = "\n{failed} could not be reached (they may have blocked the bot)."

REPORTS_SCREEN = "📊 <b>Reports</b>\nPick a period."
REPORT_BODY = (
    "📊 <b>{title}</b> · {dates}\n\n"
    "Orders placed: <b>{placed}</b>\n"
    "Confirmed: <b>{confirmed}</b> · Delivered: <b>{delivered}</b>\n"
    "Revenue: <b>{revenue} ETB</b> (food {food} + delivery {fees})\n"
    "Payments denied: <b>{denied}</b>\n"
    "Refunded: <b>{refunded}</b> ({refunded_etb} ETB) · Waiting for refund: <b>{refund_waiting}</b>\n"
    "Expired or cancelled before payment: <b>{closed_unpaid}</b>\n"
    "Customers with a confirmed order: <b>{customers}</b>\n\n"
    "<b>Top meals</b>\n{top}\n\n"
    "<i>Revenue counts only confirmed orders that were not refunded. Orders belong to the day they were placed.</i>"
)
REPORT_NO_MEALS = "No confirmed orders yet."
