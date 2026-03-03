import os
import sqlite3
import asyncio
import logging
import random
import string
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ================== CONFIG ==================

API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables")

ADMIN_ID = 7717061636   # ← غيّر هذا الرقم إلى رقمك من @userinfobot

DB_PATH = "/data/texas_global_ai.db"

os.makedirs("/data", exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================== DATABASE ==================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    subscription_until TEXT,
    trained_rounds INTEGER DEFAULT 0,
    last_hand TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS codes(
    code TEXT PRIMARY KEY,
    is_used INTEGER DEFAULT 0,
    used_by INTEGER,
    created_at TEXT,
    expires_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS games(
    rank TEXT,
    suit TEXT,
    previous_hand TEXT,
    current_hand TEXT,
    created_at TEXT
)
""")

conn.commit()

# ================== CODE GENERATION ==================

def create_subscription_code(duration_days=7):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    created_at = datetime.now().isoformat()
    if duration_days == 0:
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    else:
        expires_at = (datetime.now() + timedelta(days=duration_days)).isoformat()
    
    cursor.execute("""
    INSERT INTO codes (code, is_used, created_at, expires_at)
    VALUES (?, 0, ?, ?)
    """, (code, created_at, expires_at))
    conn.commit()
    return code, expires_at

# ================== HELPERS ==================

def check_subscription(user_id: int) -> bool:
    cursor.execute("SELECT subscription_until FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return False
    try:
        return datetime.fromisoformat(row[0]) > datetime.now()
    except:
        return False

def activate_code(user_id: int, code: str) -> tuple[bool, str]:
    cursor.execute("SELECT is_used, expires_at FROM codes WHERE code=?", (code,))
    row = cursor.fetchone()

    if not row:
        return False, "❌ الكود غير موجود"

    is_used, expires_at_str = row

    if is_used == 1:
        return False, "❌ الكود مستخدم سابقاً"

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at < datetime.now():
            return False, "❌ الكود منتهي الصلاحية"
    except:
        return False, "❌ خطأ في صلاحية الكود"

    expire_date = datetime.now() + timedelta(days=7)

    cursor.execute("""
    INSERT OR REPLACE INTO users(user_id, subscription_until, trained_rounds, last_hand)
    VALUES(?, ?, 0, NULL)
    """, (user_id, expire_date.isoformat()))

    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE code=?", (user_id, code))
    conn.commit()

    return True, f"✅ تم تفعيل الاشتراك لمدة 7 أيام\n(كان الكود صالح حتى: {expires_at.strftime('%Y-%m-%d %H:%M')})"

# ================== ADMIN COMMANDS - إضافة كود يدوي ==================

@dp.message(Command("addcode"))
async def add_custom_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("غير مصرح لك!")
        return

    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer("استخدام:\n/addcode الكود المدة\nمثال:\n/addcode MYCODE123 7\n/addcode TEST456 0")
        return

    custom_code = parts[1]
    try:
        days = int(parts[2])
    except:
        days = 7

    # تحقق إذا الكود موجود مسبقاً
    cursor.execute("SELECT code FROM codes WHERE code=?", (custom_code,))
    if cursor.fetchone():
        await message.answer("❌ هذا الكود موجود مسبقاً!")
        return

    created_at = datetime.now().isoformat()
    if days == 0:
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    else:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    cursor.execute("""
    INSERT INTO codes (code, is_used, created_at, expires_at)
    VALUES (?, 0, ?, ?)
    """, (custom_code, created_at, expires_at))
    conn.commit()

    await message.answer(f"✅ تم إضافة الكود بنجاح!\n\n`{custom_code}`\nمدة: {days} أيام\nينتهي: {expires_at.split('.')[0]}", parse_mode="MarkdownV2")

# ================== BOT FLOW ==================

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔐 إدخال الكود", callback_data="enter_code")]])
    await message.answer("اهلاً بك في بوت تخمين ضربات تكساس ♠️🔥\n\nادخل الكود حتى تبدأ الاشتراك الأسبوعي.", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "enter_code")
async def enter_code(callback: CallbackQuery):
    await callback.message.answer("🔐 ارسل الكود الآن:")
    await callback.answer()

@dp.message()
async def handle_text(message: Message):
    if message.text and message.text.strip().startswith('/'):
        return

    user_id = message.from_user.id
    text = message.text.strip()

    if not check_subscription(user_id):
        ok, msg = activate_code(user_id, text)
        await message.answer(msg)
        if ok:
            await message.answer("✅ اشتراكك مفعّل الآن!\n\nاختر رقم الورقة:", reply_markup=ranks_keyboard())
        return

    await message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())

# (باقي الـ callback handlers كما هي، يمكنك إضافتها من الكود السابق)

# ================== RUN ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook deleted, starting polling")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
