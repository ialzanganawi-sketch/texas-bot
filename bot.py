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

ADMIN_ID = 7717061636   # غيّر هذا إلى رقمك الحقيقي

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

def generate_code(length=10):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def create_subscription_code(duration_days=7):
    code = generate_code()
    while True:
        cursor.execute("SELECT code FROM codes WHERE code=?", (code,))
        if not cursor.fetchone():
            break
        code = generate_code()
    
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

    remaining = (expire_date - datetime.now()).days + 1
    return True, f"✅ تم تفعيل الاشتراك لمدة 7 أيام\n(المدة المتبقية: {remaining} أيام)"

# ================== KEYBOARDS ==================

def ranks_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=4)
    ranks = ["A","K","Q","J","10","9","8","7","6","5","4","3","2"]
    buttons = [InlineKeyboardButton(text=r, callback_data=f"rank_{r}") for r in ranks]
    kb.add(*buttons)
    return kb

def suits_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=4)
    suits = ["♥️","♦️","♣️","♠️"]
    buttons = [InlineKeyboardButton(text=s, callback_data=f"suit_{s}") for s in suits]
    kb.add(*buttons)
    return kb

def hands_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    buttons = [InlineKeyboardButton(text=h, callback_data=f"hand_{h}") for h in hands]
    kb.add(*buttons)
    return kb

# ================== ADMIN: إضافة كود يدوي ==================

@dp.message(Command("addcode"))
async def add_custom_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("غير مصرح لك!")
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("استخدام:\n/addcode الكود المدة\nمثال: /addcode MYCODE123 7")
        return

    custom_code = parts[1]
    days = 7
    if len(parts) > 2:
        try:
            days = int(parts[2])
        except:
            days = 7

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

    await message.answer(f"✅ تم إضافة الكود بنجاح!\n\n`{custom_code}`\nمدة: {days} أيام", parse_mode="MarkdownV2")

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
    user_id = message.from_user.id
    text = message.text.strip()

    if not check_subscription(user_id):
        ok, msg = activate_code(user_id, text)
        await message.answer(msg)

        if ok:
            # زر بدء التخمين بعد التفعيل
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎮 بدء التخمين", callback_data="start_guessing")]])
            await message.answer("اختر الآن:", reply_markup=kb)
        return

    await message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())

# ================== زر بدء التخمين ==================

@dp.callback_query(lambda c: c.data == "start_guessing")
async def start_guessing(callback: CallbackQuery):
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())
    await callback.answer()

# ================== باقي الـ Callbacks ==================

@dp.callback_query(lambda c: c.data.startswith("rank_"))
async def choose_rank(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_temp[user_id] = {"rank": callback.data.split("_")[1]}
    await callback.message.answer("اختر نوع الورقة:", reply_markup=suits_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def choose_suit(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_temp[user_id]["suit"] = callback.data.split("_")[1]

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        await callback.message.answer("خطأ في قاعدة البيانات، جرب /start مرة أخرى")
        await callback.answer()
        return

    trained, last_hand = row

    if trained < 3:
        await callback.message.answer(f"⚠️ جولة تدريب رقم {trained+1} من 3\n\nشنو كانت ضربتك؟", reply_markup=hands_keyboard())
    else:
        prediction = predict_hand(user_temp[user_id]["rank"], user_temp[user_id]["suit"], last_hand)
        await callback.message.answer(f"🤖 تخميني:\n\n{prediction}")
        await callback.message.answer("شنو كانت ضربتك الحقيقية؟", reply_markup=hands_keyboard())

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hand_"))
async def choose_hand(callback: CallbackQuery):
    user_id = callback.from_user.id
    current_hand = callback.data.replace("hand_", "")

    if user_id not in user_temp or "rank" not in user_temp[user_id] or "suit" not in user_temp[user_id]:
        await callback.message.answer("خطأ في التسلسل، جرب من جديد")
        await callback.answer()
        return

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        await callback.message.answer("خطأ في قاعدة البيانات")
        await callback.answer()
        return

    trained, previous_hand = row

    save_game(user_temp[user_id]["rank"], user_temp[user_id]["suit"], previous_hand, current_hand)

    trained += 1

    cursor.execute("UPDATE users SET trained_rounds=?, last_hand=? WHERE user_id=?", (trained, current_hand, user_id))
    conn.commit()

    await callback.message.answer("✅ تم حفظ الجولة.\n\nاختر رقم الورقة الجديدة:")
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())

    user_temp.pop(user_id, None)
    await callback.answer()

# ================== RUN ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook deleted, starting polling")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
