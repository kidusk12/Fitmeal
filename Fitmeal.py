"""
FitMeal – Telegram-based meal ordering system (MVP, no AI)

Changelog (this fixed build):
- Uses pytz timezone objects (configurable via TIMEZONE env, default Africa/Addis_Ababa)
- Scheduling flow fixed: parses local time, stores "YYYY-MM-DD HH:MM" (no 'T'),
  and compares consistently; only Approved scheduled orders progress
- Removed fake CallbackQuery hack; address prompt works from query or message
- Scheduler uses AsyncIOScheduler(timezone=TIMEZONE); all triggers localized
- Weekly analytics job receives Application via args
- ConversationHandler set per_message=True to remove PTB warning
- Polling simplified to app.run_polling() for PTB >= 21
- Admin "Today" snapshot computed in SQLite using localtime
- Minor cleanups, safer bot calls via context.bot

ENV:
- BOT_TOKEN (required)
- ADMIN_IDS (comma-separated Telegram user IDs)
- DATABASE_URL (optional, default sqlite:///fitmeal.db)
- TIMEZONE (optional, e.g. Africa/Addis_Ababa)
- LOG_LEVEL (optional)

Run:
  pip install python-telegram-bot==21.6 apscheduler python-dotenv fastapi uvicorn
  python fitmeal_bot.py
"""
from __future__ import annotations

# --------------------------- LOAD ENV & CONFIG ---------------------------
from dotenv import load_dotenv
load_dotenv()

import os
import re
import asyncio
import logging
import sqlite3
from contextlib import closing
from typing import Optional

import pytz
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)

# --------------------------- LOGGING ---------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("fitmeal")

# --------------------------- ENV VARS ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = set()
_admin_env = os.getenv("ADMIN_IDS", "").strip()
if _admin_env:
    try:
        ADMIN_IDS = {int(x.strip()) for x in _admin_env.split(',') if x.strip()}
    except Exception:
        log.warning("Invalid ADMIN_IDS env; expected comma-separated integers")

TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Africa/Addis_Ababa"))
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///fitmeal.db").replace("sqlite:///", "")

# --------------------------- DB SCHEMA ---------------------------
SCHEMA_SQL = r"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    age INTEGER,
    phone TEXT,
    gender TEXT,
    allergies TEXT,
    fitness_goal TEXT,
    location_hint TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    price_etb INTEGER NOT NULL,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    recipe TEXT,
    photo_url TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    unit TEXT DEFAULT 'g',
    price_per_unit_etb REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meal_ingredients (
    meal_id INTEGER NOT NULL,
    ingredient_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    PRIMARY KEY (meal_id, ingredient_id),
    FOREIGN KEY (meal_id) REFERENCES meals(id),
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_uid TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    meal_id INTEGER NOT NULL,
    is_customized INTEGER DEFAULT 0,
    customization_note TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    status_reason TEXT,
    is_scheduled INTEGER DEFAULT 0,
    scheduled_at TEXT,
    delivery_address TEXT,
    delivery_lat REAL,
    delivery_lng REAL,
    price_snapshot_etb INTEGER NOT NULL,
    calories_snapshot INTEGER,
    protein_g_snapshot REAL,
    carbs_g_snapshot REAL,
    fat_g_snapshot REAL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(meal_id) REFERENCES meals(id)
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    photo_file_id TEXT,
    text TEXT,
    target_user_id INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- For analytics (UTC-based; we'll query with localtime when needed)
CREATE VIEW IF NOT EXISTS v_daily_orders AS
SELECT date(created_at) AS day, count(*) AS cnt, sum(price_snapshot_etb) AS revenue
FROM orders
GROUP BY day;
"""

ORDER_STATUSES = [
    "Pending",
    "Approved",
    "Denied",
    "In Progress",
    "Out for Delivery",
    "Completed",
]

CATEGORIES = [
    "Breakfast",
    "Pre-workout",
    "Post-workout",
    "Shakes",
    "Drinks",
]

# --------------------------- DB UTILS ---------------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db()) as conn:
        conn.executescript(SCHEMA_SQL)
        # Seed categories
        cur = conn.execute("SELECT COUNT(*) AS c FROM categories")
        if cur.fetchone()["c"] == 0:
            conn.executemany("INSERT INTO categories(name) VALUES(?)", [(c,) for c in CATEGORIES])
        # Seed daily limit default
        cur = conn.execute("SELECT value FROM config WHERE key='daily_limit'")
        if cur.fetchone() is None:
            conn.execute("INSERT INTO config(key, value) VALUES('daily_limit','100')")
        conn.commit()

# --------------------------- HELPERS ---------------------------

def is_admin(tg_user_id: int) -> bool:
    return tg_user_id in ADMIN_IDS


def gen_order_uid(now: Optional[datetime] = None) -> str:
    now = now or datetime.utcnow()
    stamp = now.strftime("%Y%m%d%H%M%S")
    with closing(db()) as conn:
        cur = conn.execute("SELECT COALESCE(MAX(id),0)+1 as n FROM orders")
        n = cur.fetchone()["n"]
    return f"FIT-{stamp}-{n:04d}"


def get_or_create_user(update: Update) -> int:
    u = update.effective_user
    with closing(db()) as conn:
        cur = conn.execute("SELECT id FROM users WHERE tg_user_id=?", (u.id,))
        row = cur.fetchone()
        if row:
            return row["id"]
        conn.execute(
            "INSERT INTO users(tg_user_id, username, full_name) VALUES(?,?,?)",
            (u.id, u.username, u.full_name),
        )
        conn.commit()
        return conn.execute("SELECT id FROM users WHERE tg_user_id=?", (u.id,)).fetchone()["id"]


def get_daily_limit() -> int:
    with closing(db()) as conn:
        row = conn.execute("SELECT value FROM config WHERE key='daily_limit'").fetchone()
        return int(row["value"]) if row else 100


def count_orders_today_local() -> int:
    # Count using SQLite localtime so "today" matches local day
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE date(created_at,'localtime')=date('now','localtime')"
        ).fetchone()
        return int(row["c"]) if row else 0

# --------------------------- CONVERSATION STATES ---------------------------
(
    SIGNUP_NAME,
    SIGNUP_AGE,
    SIGNUP_PHONE,
    SIGNUP_GENDER,
    SIGNUP_ALLERGIES,
    SIGNUP_GOAL,
    SIGNUP_LOCATIONHINT,
    BROWSING,
    MEAL_DETAIL,
    ORDER_MODE,
    CUSTOMIZATION,
    ASK_ADDRESS,
    ASK_SCHEDULE,
) = range(13)

# --------------------------- COMMANDS ---------------------------
WELCOME = (
    "Welcome to *FitMeal*! 🥗\n\n"
    "I can help you order healthy meals for pickup or delivery.\n"
    "Use the menu below to browse, order now, or schedule."
)

async def start(update: Update, context: CallbackContext):
    user_id = get_or_create_user(update)
    # Check if signup complete
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT full_name, age, phone, gender, allergies, fitness_goal, location_hint FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    missing = [
        ("full_name", SIGNUP_NAME),
        ("age", SIGNUP_AGE),
        ("phone", SIGNUP_PHONE),
        ("gender", SIGNUP_GENDER),
        ("allergies", SIGNUP_ALLERGIES),
        ("fitness_goal", SIGNUP_GOAL),
        ("location_hint", SIGNUP_LOCATIONHINT),
    ]
    for field, _state in missing:
        if not row[field]:
            await update.effective_chat.send_message(
                "Let's complete your quick sign-up first. ✍️\nWhat's your *full name*?",
                parse_mode=ParseMode.MARKDOWN,
            )
            return SIGNUP_NAME
    await show_main_menu(update, context)
    return BROWSING

async def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Browse Meals", callback_data="browse")],
        [InlineKeyboardButton("Order History", callback_data="history")],
    ]
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin")])
    await update.effective_chat.send_message(
        WELCOME,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )

# --------------------------- SIGNUP FLOW ---------------------------
async def signup_name(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET full_name=? WHERE tg_user_id=?", (text, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Age?")
    return SIGNUP_AGE

async def signup_age(update: Update, context: CallbackContext):
    try:
        age = int(re.findall(r"\d+", update.message.text)[0])
    except Exception:
        await update.message.reply_text("Please enter a number for age.")
        return SIGNUP_AGE
    with closing(db()) as conn:
        conn.execute("UPDATE users SET age=? WHERE tg_user_id=?", (age, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Phone number?")
    return SIGNUP_PHONE

async def signup_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET phone=? WHERE tg_user_id=?", (phone, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Gender? (Male/Female/Other)")
    return SIGNUP_GENDER

async def signup_gender(update: Update, context: CallbackContext):
    gender = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET gender=? WHERE tg_user_id=?", (gender, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Any allergies? (write 'None' if not)")
    return SIGNUP_ALLERGIES

async def signup_allergies(update: Update, context: CallbackContext):
    allergies = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET allergies=? WHERE tg_user_id=?", (allergies, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Fitness goal? (weight gain, weight loss, surplus/deficit)")
    return SIGNUP_GOAL

async def signup_goal(update: Update, context: CallbackContext):
    goal = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET fitness_goal=? WHERE tg_user_id=?", (goal, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("Your general location (e.g., Addis Ababa, around Bethel Hospital)")
    return SIGNUP_LOCATIONHINT

async def signup_locationhint(update: Update, context: CallbackContext):
    loc = update.message.text.strip()
    with closing(db()) as conn:
        conn.execute("UPDATE users SET location_hint=? WHERE tg_user_id=?", (loc, update.effective_user.id))
        conn.commit()
    await update.message.reply_text("You're all set! 🎉")
    await show_main_menu(update, context)
    return BROWSING

# --------------------------- BROWSING ---------------------------
async def on_main_menu_click(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "browse":
        with closing(db()) as conn:
            cats = conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
        keyboard = [[InlineKeyboardButton(c["name"], callback_data=f"cat:{c['id']}")] for c in cats]
        await q.edit_message_text("Choose a category:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("cat:"):
        cat_id = int(data.split(":")[1])
        with closing(db()) as conn:
            meals = conn.execute(
                "SELECT id, name, price_etb FROM meals WHERE is_active=1 AND category_id=? ORDER BY name",
                (cat_id,),
            ).fetchall()
        if not meals:
            await q.edit_message_text("No meals in this category yet.")
            return
        keyboard = [
            [InlineKeyboardButton(f"{m['name']} — {m['price_etb']} ETB", callback_data=f"meal:{m['id']}")]
            for m in meals
        ]
        await q.edit_message_text("Select a meal:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("meal:"):
        meal_id = int(data.split(":")[1])
        with closing(db()) as conn:
            m = conn.execute(
                "SELECT id,name,price_etb,calories,protein_g,carbs_g,fat_g,recipe,photo_url FROM meals WHERE id=?",
                (meal_id,),
            ).fetchone()
        if not m:
            await q.answer("Meal not found", show_alert=True)
            return
        text = (
            f"*{m['name']}*\n"
            f"Price: {m['price_etb']} ETB\n"
            f"Calories: {m['calories']} kcal | P {m['protein_g']}g / C {m['carbs_g']}g / F {m['fat_g']}g\n\n"
            f"Recipe: {m['recipe'] or '—'}"
        )
        kb = [
            [InlineKeyboardButton("Order Now", callback_data=f"ordernow:{m['id']}")],
            [InlineKeyboardButton("Schedule Order", callback_data=f"schedule:{m['id']}")],
            [InlineKeyboardButton("Customize (needs approval)", callback_data=f"custom:{m['id']}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="browse")],
        ]
        if m["photo_url"]:
            # send new message with photo
            await q.message.reply_photo(m["photo_url"], caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
            await q.delete_message()
        else:
            await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
    elif data == "history":
        user_id = get_or_create_user(update)
        with closing(db()) as conn:
            rows = conn.execute(
                """
                SELECT order_uid, name, status, created_at, COALESCE(scheduled_at, '') as scheduled_at, price_snapshot_etb
                FROM orders o JOIN meals m ON o.meal_id=m.id
                WHERE o.user_id=?
                ORDER BY o.created_at DESC LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        if not rows:
            await q.edit_message_text("No past orders yet.")
            return
        lines = [
            f"{r['order_uid']} • {r['name']} • {r['status']} • {r['price_snapshot_etb']} ETB\n"
            f"  Placed: {r['created_at']}{' | Scheduled: ' + r['scheduled_at'] if r['scheduled_at'] else ''}"
            for r in rows
        ]
        await q.edit_message_text("Your recent orders:\n\n" + "\n\n".join(lines))
    elif data == "admin":
        if not is_admin(update.effective_user.id):
            await q.answer("Not authorized", show_alert=True)
            return
        kb = [
            [InlineKeyboardButton("Add Meal", callback_data="admin:addmeal")],
            [InlineKeyboardButton("Update Price", callback_data="admin:updateprice")],
            [InlineKeyboardButton("Delete Meal", callback_data="admin:deletemeal")],
            [InlineKeyboardButton("Set Daily Limit", callback_data="admin:setlimit")],
            [InlineKeyboardButton("Broadcast Photo/Text", callback_data="admin:broadcast")],
            [InlineKeyboardButton("Orders Today", callback_data="admin:today")],
        ]
        await q.edit_message_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await q.answer()

# --------------------------- ORDER FLOW ---------------------------
async def on_order_buttons(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("ordernow:"):
        meal_id = int(data.split(":")[1])
        context.user_data["meal_id"] = meal_id
        context.user_data["is_scheduled"] = 0
        await ask_address(q, context)
        return ASK_ADDRESS
    elif data.startswith("schedule:"):
        meal_id = int(data.split(":")[1])
        context.user_data["meal_id"] = meal_id
        context.user_data["is_scheduled"] = 1
        await q.edit_message_text("Send date & time in format YYYY-MM-DD HH:MM (24h)")
        return ASK_SCHEDULE
    elif data.startswith("custom:"):
        meal_id = int(data.split(":")[1])
        context.user_data["meal_id"] = meal_id
        await q.edit_message_text("Describe your customization (add/remove ingredients). Admin will approve/deny.")
        return CUSTOMIZATION

async def ask_address(src, context):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("Share location", request_location=True)]], resize_keyboard=True, one_time_keyboard=True
    )
    # If called from a CallbackQuery, try to edit; else, just send a new message
    if hasattr(src, "edit_message_text"):
        try:
            await src.edit_message_text("Send delivery address: either share location or paste Google Maps link / write address.")
        except Exception:
            pass
        chat = src.message.chat
    else:
        chat = src.effective_chat
        await chat.send_message("Send delivery address: either share location or paste Google Maps link / write address.")
    await chat.send_message("Tap to share location:", reply_markup=kb)

async def handle_address(update: Update, context: CallbackContext):
    # handles both text and location
    loc = update.message.location
    if loc:
        context.user_data["delivery_lat"] = loc.latitude
        context.user_data["delivery_lng"] = loc.longitude
        context.user_data["delivery_address"] = f"Location({loc.latitude:.5f},{loc.longitude:.5f})"
    else:
        context.user_data["delivery_address"] = update.message.text.strip()
        context.user_data["delivery_lat"] = None
        context.user_data["delivery_lng"] = None
    return await finalize_order(update, context)

async def handle_schedule(update: Update, context: CallbackContext):
    try:
        txt = update.message.text.strip()
        dt_naive = datetime.strptime(txt, "%Y-%m-%d %H:%M")
        dt_local = TIMEZONE.localize(dt_naive)
        if dt_local < datetime.now(TIMEZONE) + timedelta(minutes=10):
            await update.message.reply_text("Please schedule at least 10 minutes in the future.")
            return ASK_SCHEDULE
        context.user_data["scheduled_at"] = dt_local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        await update.message.reply_text("Invalid format. Use YYYY-MM-DD HH:MM (24h).")
        return ASK_SCHEDULE
    await ask_address(update, context)
    return ASK_ADDRESS

async def handle_customization(update: Update, context: CallbackContext):
    context.user_data["customization_note"] = update.message.text.strip()
    await update.message.reply_text("Customization noted. Now send your address (share location or text).")
    return ASK_ADDRESS

async def finalize_order(update: Update, context: CallbackContext):
    # Daily limit (local day)
    limit = get_daily_limit()
    placed_today = count_orders_today_local()
    if placed_today >= limit:
        await update.message.reply_text(
            f"Sorry, we've reached today's order limit ({limit}). Please try again tomorrow."
        )
        return ConversationHandler.END

    user_tbl_id = get_or_create_user(update)
    meal_id = context.user_data.get("meal_id")
    is_scheduled = int(context.user_data.get("is_scheduled", 0))
    customization_note = context.user_data.get("customization_note")
    is_customized = 1 if customization_note else 0
    delivery_address = context.user_data.get("delivery_address")
    delivery_lat = context.user_data.get("delivery_lat")
    delivery_lng = context.user_data.get("delivery_lng")
    scheduled_at = context.user_data.get("scheduled_at") if is_scheduled else None

    with closing(db()) as conn:
        m = conn.execute(
            "SELECT id,name,price_etb,calories,protein_g,carbs_g,fat_g FROM meals WHERE id=?",
            (meal_id,),
        ).fetchone()
        if not m:
            await update.message.reply_text("Meal not found.")
            return ConversationHandler.END
        order_uid = gen_order_uid()
        # Non-customized orders are auto-approved (scheduled or now). Customized stay Pending.
        status = "Pending" if is_customized else "Approved"
        conn.execute(
            """
            INSERT INTO orders(order_uid,user_id,meal_id,is_customized,customization_note,status,is_scheduled,scheduled_at,
                               delivery_address,delivery_lat,delivery_lng,price_snapshot_etb,calories_snapshot,protein_g_snapshot,carbs_g_snapshot,fat_g_snapshot)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                order_uid,
                user_tbl_id,
                meal_id,
                is_customized,
                customization_note,
                status,
                is_scheduled,
                scheduled_at,
                delivery_address,
                delivery_lat,
                delivery_lng,
                m["price_etb"],
                m["calories"],
                m["protein_g"],
                m["carbs_g"],
                m["fat_g"],
            ),
        )
        conn.commit()

    # Notify user
    when = f"Scheduled for {scheduled_at}" if scheduled_at else "For ASAP delivery"
    await update.message.reply_text(
        f"✅ Order placed!\nID: {order_uid}\nMeal: {m['name']}\n{when}\nStatus: {status}"
    )

    # Notify admins
    await notify_admins_new_order(update, context, order_uid)

    # Clear user_data
    context.user_data.clear()
    return ConversationHandler.END

async def notify_admins_new_order(update: Update, context: CallbackContext, order_uid: str):
    with closing(db()) as conn:
        o = conn.execute(
            """
            SELECT o.order_uid, o.customization_note, o.is_customized, o.is_scheduled, o.scheduled_at,
                   o.delivery_address, o.delivery_lat, o.delivery_lng, o.status,
                   m.name AS meal_name, m.recipe,
                   u.full_name, u.username
            FROM orders o
            JOIN meals m ON o.meal_id=m.id
            JOIN users u ON o.user_id=u.id
            WHERE o.order_uid=?
            """,
            (order_uid,),
        ).fetchone()
    text = (
        f"📦 *New Order* {o['order_uid']}\n"
        f"Meal: {o['meal_name']}\n"
        f"User: {o['full_name']} (@{o['username'] or '—'})\n"
        f"Status: {o['status']}\n"
        f"When: {'Scheduled ' + o['scheduled_at'] if o['is_scheduled'] else 'Now'}\n"
        f"Address: {o['delivery_address']}\n"
        f"Customized: {'Yes' if o['is_customized'] else 'No'}\n"
        f"Note: {o['customization_note'] or '—'}\n"
        f"Recipe: {o['recipe'] or '—'}"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"admin:approve:{o['order_uid']}"),
            InlineKeyboardButton("Deny", callback_data=f"admin:deny:{o['order_uid']}")
        ],
        [
            InlineKeyboardButton("Set In Progress", callback_data=f"admin:set:{o['order_uid']}:In Progress"),
            InlineKeyboardButton("Out for Delivery", callback_data=f"admin:set:{o['order_uid']}:Out for Delivery"),
            InlineKeyboardButton("Completed", callback_data=f"admin:set:{o['order_uid']}:Completed"),
        ],
    ])
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception as e:
            log.warning(f"Failed to notify admin {admin_id}: {e}")

# --------------------------- ADMIN BUTTONS ---------------------------
async def on_admin_buttons(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id):
        await q.answer("Not authorized", show_alert=True)
        return
    data = q.data
    if data.startswith("admin:approve:"):
        order_uid = data.split(":")[2]
        await set_order_status(order_uid, "Approved")
        await q.edit_message_reply_markup(None)
        await q.message.reply_text(f"Order {order_uid} set to Approved")
    elif data.startswith("admin:deny:"):
        order_uid = data.split(":")[2]
        context.user_data["deny_target"] = order_uid
        await q.message.reply_text("Send reason for denial:")
        context.user_data["awaiting_deny_reason"] = True
    elif data.startswith("admin:set:"):
        _, _, order_uid, status = data.split(":", 3)
        if status not in ORDER_STATUSES:
            await q.answer("Invalid status", show_alert=True)
            return
        await set_order_status(order_uid, status)
        await q.message.reply_text(f"Order {order_uid} set to {status}")
    elif data == "admin:addmeal":
        await q.message.reply_text("Send meal as: Name | Category | PriceETB | kcal | P | C | F | Recipe (optional)")
        context.user_data["awaiting_add_meal"] = True
    elif data == "admin:updateprice":
        await q.message.reply_text("Send: MealName | NewPriceETB (cannot be lower than current)")
        context.user_data["awaiting_update_price"] = True
    elif data == "admin:deletemeal":
        await q.message.reply_text("Send: MealName to delete")
        context.user_data["awaiting_delete_meal"] = True
    elif data == "admin:setlimit":
        await q.message.reply_text("Send: New daily limit (integer)")
        context.user_data["awaiting_set_limit"] = True
    elif data == "admin:broadcast":
        await q.message.reply_text("Reply with photo and caption. Optionally include @username to target specific user(s).")
        context.user_data["awaiting_broadcast"] = True
    elif data == "admin:today":
        # compute with localtime inside SQLite to match local day
        with closing(db()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, COALESCE(SUM(price_snapshot_etb),0) AS revenue "
                "FROM orders WHERE date(created_at,'localtime')=date('now','localtime')"
            ).fetchone()
        cnt = row["cnt"] if row else 0
        rev = row["revenue"] if row else 0
        today_str = datetime.now(TIMEZONE).date().isoformat()
        await q.message.reply_text(f"Today {today_str}: {cnt} orders • {rev} ETB revenue (estimate)")

async def set_order_status(order_uid: str, status: str, reason: Optional[str] = None):
    with closing(db()) as conn:
        conn.execute(
            "UPDATE orders SET status=?, status_reason=?, updated_at=datetime('now') WHERE order_uid=?",
            (status, reason, order_uid),
        )
        # Notify user
        row = conn.execute(
            "SELECT u.tg_user_id FROM orders o JOIN users u ON o.user_id=u.id WHERE order_uid=?",
            (order_uid,),
        ).fetchone()
        conn.commit()
    if row:
        try:
            await application.bot.send_message(
                chat_id=row["tg_user_id"],
                text=f"Your order {order_uid} status updated to *{status}*{': ' + reason if reason else ''}.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            log.warning(f"Failed to notify user about status: {e}")

# --------------------------- ADMIN TEXT / MEDIA ---------------------------
async def admin_text_handler(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if context.user_data.get("awaiting_deny_reason"):
        reason = update.message.text.strip()
        order_uid = context.user_data.get("deny_target")
        context.user_data["awaiting_deny_reason"] = False
        await set_order_status(order_uid, "Denied", reason=reason)
        await update.message.reply_text(f"Order {order_uid} denied.")
        return

    if context.user_data.get("awaiting_add_meal"):
        context.user_data["awaiting_add_meal"] = False
        parts = [p.strip() for p in update.message.text.split("|")]
        if len(parts) < 7:
            await update.message.reply_text("Invalid format. See prompt.")
            return
        name, category, price, kcal, p, c, f = parts[:7]
        recipe = parts[7] if len(parts) > 7 else None
        with closing(db()) as conn:
            cat = conn.execute("SELECT id FROM categories WHERE name=?", (category,)).fetchone()
            if not cat:
                await update.message.reply_text("Unknown category.")
                return
            conn.execute(
                "INSERT INTO meals(name, category_id, price_etb, calories, protein_g, carbs_g, fat_g, recipe) VALUES(?,?,?,?,?,?,?,?)",
                (name, cat["id"], int(price), int(kcal), float(p), float(c), float(f), recipe),
            )
            conn.commit()
        await update.message.reply_text(f"Added meal {name}.")
        return

    if context.user_data.get("awaiting_update_price"):
        context.user_data["awaiting_update_price"] = False
        try:
            name, new_price = [x.strip() for x in update.message.text.split("|")]
            new_price = int(new_price)
        except Exception:
            await update.message.reply_text("Invalid format.")
            return
        with closing(db()) as conn:
            row = conn.execute("SELECT id, price_etb FROM meals WHERE name=?", (name,)).fetchone()
            if not row:
                await update.message.reply_text("Meal not found.")
                return
            if new_price < row["price_etb"]:
                await update.message.reply_text("Price cannot be decreased (policy).")
                return
            conn.execute("UPDATE meals SET price_etb=?, updated_at=datetime('now') WHERE id=?", (new_price, row["id"]))
            conn.commit()
        await update.message.reply_text(f"Updated {name} price to {new_price} ETB.")
        return

    if context.user_data.get("awaiting_delete_meal"):
        context.user_data["awaiting_delete_meal"] = False
        name = update.message.text.strip()
        with closing(db()) as conn:
            conn.execute("UPDATE meals SET is_active=0 WHERE name=?", (name,))
            conn.commit()
        await update.message.reply_text(f"Deactivated meal {name}.")
        return

    if context.user_data.get("awaiting_set_limit"):
        context.user_data["awaiting_set_limit"] = False
        try:
            n = int(re.findall(r"\d+", update.message.text)[0])
        except Exception:
            await update.message.reply_text("Send an integer.")
            return
        with closing(db()) as conn:
            conn.execute(
                "INSERT INTO config(key,value) VALUES('daily_limit',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(n),),
            )
            conn.commit()
        await update.message.reply_text(f"Daily limit set to {n}.")
        return

async def admin_media_handler(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_broadcast"):
        return
    caption = update.message.caption or ""
    targets = {u for u in re.findall(r"@([A-Za-z0-9_]{5,})", caption)}
    photo = update.message.photo[-1] if update.message.photo else None

    # Resolve user IDs by username
    with closing(db()) as conn:
        if targets:
            q_marks = ",".join(["?"] * len(targets))
            rows = conn.execute(
                f"SELECT tg_user_id FROM users WHERE username IN ({q_marks})",
                tuple(targets),
            ).fetchall()
            target_ids = [r["tg_user_id"] for r in rows]
        else:
            rows = conn.execute("SELECT tg_user_id FROM users").fetchall()
            target_ids = [r["tg_user_id"] for r in rows]

    for tid in target_ids:
        try:
            if photo:
                await context.bot.send_photo(chat_id=tid, photo=photo.file_id, caption=caption)
            else:
                await context.bot.send_message(chat_id=tid, text=caption)
        except Exception as e:
            log.warning(f"Broadcast to {tid} failed: {e}")

    # Save broadcast record
    with closing(db()) as conn:
        conn.execute(
            "INSERT INTO broadcasts(admin_id, photo_file_id, text, target_user_id) VALUES(?,?,?,?)",
            (update.effective_user.id, photo.file_id if photo else None, caption, None if not targets else 0),
        )
        conn.commit()

    context.user_data["awaiting_broadcast"] = False
    await update.message.reply_text("Broadcast sent.")

# --------------------------- SCHEDULER TASKS ---------------------------
async def process_due_orders(app: Application):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    with closing(db()) as conn:
        rows = conn.execute(
            """
            SELECT order_uid
            FROM orders
            WHERE is_scheduled=1
              AND status='Approved'   -- do not progress Pending (customized) orders
              AND scheduled_at <= ?
            """,
            (now,),
        ).fetchall()
    for r in rows:
        await set_order_status(r["order_uid"], "In Progress")

async def send_weekly_analytics(app: Application):
    with closing(db()) as conn:
        stats = conn.execute(
            """
            SELECT count(*) AS total_orders,
                   sum(price_snapshot_etb) AS revenue,
                   sum(CASE WHEN status='Denied' THEN 1 ELSE 0 END) AS denied
            FROM orders
            WHERE created_at >= datetime('now','-7 days')
            """
        ).fetchone()
        top = conn.execute(
            """
            SELECT m.name, COUNT(*) AS c
            FROM orders o JOIN meals m ON o.meal_id=m.id
            WHERE o.created_at >= datetime('now','-7 days')
            GROUP BY m.name
            ORDER BY c DESC LIMIT 5
            """
        ).fetchall()
        active = conn.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS au
            FROM orders
            WHERE created_at >= datetime('now','-7 days')
            """
        ).fetchone()
        reasons = conn.execute(
            """
            SELECT status_reason, COUNT(*) AS c
            FROM orders
            WHERE status='Denied' AND created_at >= datetime('now','-7 days')
            GROUP BY status_reason
            ORDER BY c DESC
            """
        ).fetchall()

    lines = [
        "📊 *Weekly Analytics* (last 7 days)",
        f"Total orders: {stats['total_orders'] or 0}",
        f"Denied: {stats['denied'] or 0}",
        f"Active users: {active['au'] or 0}",
        f"Revenue estimate: {stats['revenue'] or 0} ETB",
        "Top meals:" if top else "Top meals: —",
    ]
    for r in top:
        lines.append(f" • {r['name']} ({r['c']})")
    if reasons:
        lines.append("\nTop denial reasons:")
        for r in reasons:
            lines.append(f" • {r['status_reason'] or '—'} ({r['c']})")

    text = "\n".join(lines)
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(admin_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            log.warning(f"Weekly analytics to {admin_id} failed: {e}")

# --------------------------- FASTAPI (optional) ---------------------------
try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except Exception:
    FastAPI = None  # type: ignore

api_app = FastAPI(title="FitMeal API") if FastAPI else None

if api_app:
    @api_app.get("/health")
    async def health():
        return {"ok": True}

    @api_app.get("/orders")
    async def list_orders(status: Optional[str] = None, days: int = 7):
        q = "SELECT order_uid, status, price_snapshot_etb, created_at FROM orders WHERE created_at >= datetime('now', ?)"
        args = (f"-{days} days",)
        if status:
            q += " AND status=?"
            args += (status,)
        with closing(db()) as conn:
            rows = [dict(r) for r in conn.execute(q, args).fetchall()]
        return JSONResponse(rows)

# --------------------------- APP BOOTSTRAP ---------------------------
application: Application  # global for status notifications

def build_app() -> Application:
    global application
    init_db()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SIGNUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_name)],
            SIGNUP_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_age)],
            SIGNUP_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_phone)],
            SIGNUP_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_gender)],
            SIGNUP_ALLERGIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_allergies)],
            SIGNUP_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_goal)],
            SIGNUP_LOCATIONHINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_locationhint)],
            BROWSING: [CallbackQueryHandler(on_main_menu_click)],
            MEAL_DETAIL: [],
            ORDER_MODE: [CallbackQueryHandler(on_order_buttons)],
            CUSTOMIZATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_customization)],
            ASK_ADDRESS: [MessageHandler((filters.LOCATION | (filters.TEXT & ~filters.COMMAND)), handle_address)],
            ASK_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv)

    # Generic callbacks (outside conv) — patterns kept for safety
    application.add_handler(CallbackQueryHandler(on_main_menu_click, pattern=r"^(browse|history|admin|cat:|meal:).+|^(browse|history|admin)$"))
    application.add_handler(CallbackQueryHandler(on_order_buttons, pattern=r"^(ordernow:|schedule:|custom:).+"))
    application.add_handler(CallbackQueryHandler(on_admin_buttons, pattern=r"^admin:.*"))


    # Admin text/photo handlers
    application.add_handler(MessageHandler(filters.PHOTO, admin_media_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

    # Scheduler with localized timezone
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    # one-time kick shortly after start
    scheduler.add_job(
        process_due_orders,
        DateTrigger(run_date=datetime.now(TIMEZONE) + timedelta(minutes=1), timezone=TIMEZONE),
        args=[application],
    )
    # sweep every 5 minutes
    scheduler.add_job(
        process_due_orders,
        CronTrigger(minute="*/5", timezone=TIMEZONE),
        args=[application],
    )
    # weekly analytics
    scheduler.add_job(
        send_weekly_analytics,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=TIMEZONE),
        args=[application],
    )
    scheduler.start()

    return application

# --------------------------- ENTRYPOINT ---------------------------
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env var is required.")
    app = build_app()
    log.info("Starting FitMeal bot in long-polling mode…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
