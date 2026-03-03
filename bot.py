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

ADMIN_ID = 7717061636  # غيره إلى رقمك

DB_PATH = "texas_bot.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_temp = {}  # تخزين مؤقت لاختيار الورقة

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

# ================== HELPERS ==================

def generate_code(length=8):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def create_subscription_code(days=7):
    code = generate_code()
    created_at = datetime.now().isoformat()
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    cursor.execute("""
    INSERT INTO codes (code, is_used, created_at, expires_at)
    VALUES (?, 0, ?, ?)
    """, (code, created_at, expires_at))
    conn.commit()
    return code

def check_subscription(user_id: int):
    cursor.execute("SELECT subscription_until FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return False
    return datetime.fromisoformat(row[0]) > datetime.now()

def activate_code(user_id: int, code: str):
    cursor.execute("SELECT is_used, expires_at FROM codes WHERE code=?", (code,))
    row = cursor.fetchone()

    if not row:
        return False, "❌ الكود غير موجود"

    is_used, expires_at = row

    if is_used:
        return False, "❌ الكود مستخدم"

    if datetime.fromisoformat(expires_at) < datetime.now():
        return False, "❌ الكود منتهي"

    expire_date = datetime.now() + timedelta(days=7)

    cursor.execute("""
    INSERT OR REPLACE INTO users(user_id, subscription_until, trained_rounds, last_hand)
    VALUES(?, ?, 0, NULL)
    """, (user_id, expire_date.isoformat()))

    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE code=?", (user_id, code))
    conn.commit()

    return True, "✅ تم تفعيل الاشتراك لمدة 7 أيام"

def save_game(rank, suit, previous_hand, current_hand):
    cursor.execute("""
    INSERT INTO games(rank, suit, previous_hand, current_hand, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (rank, suit, previous_hand, current_hand, datetime.now().isoformat()))
    conn.commit()

def predict_hand(rank, suit, last_hand):
    # تخمين بسيط عشوائي (يمكن تطويره لاحقاً)
    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    return random.choice(hands)

# ================== KEYBOARDS ==================

def ranks_keyboard():
    ranks = ["A","K","Q","J","10","9","8","7","6","5","4","3","2"]
    buttons = [[InlineKeyboardButton(text=r, callback_data=f"rank_{r}") for r in ranks[i:i+4]] for i in range(0, len(ranks), 4)]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def suits_keyboard():
    suits = ["♥️","♦️","♣️","♠️"]
    buttons = [[InlineKeyboardButton(text=s, callback_data=f"suit_{s}") for s in suits]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def hands_keyboard():
    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    buttons = [[InlineKeyboardButton(text=h, callback_data=f"hand_{h}")] for h in hands]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================== ADMIN ==================

@dp.message(Command("addcode"))
async def add_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("غير مصرح")
        return

    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 else 7

    code = create_subscription_code(days)
    await message.answer(f"✅ الكود:\n`{code}`", parse_mode="Markdown")

# ================== START ==================

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 إدخال الكود", callback_data="enter_code")]
    ])
    await message.answer("🔥 اهلاً بك في بوت تكساس\nادخل الكود لتفعيل الاشتراك", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "enter_code")
async def enter_code(callback: CallbackQuery):
    await callback.message.answer("🔐 ارسل الكود الآن:")
    await callback.answer()

@dp.message()
async def handle_code(message: Message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        ok, msg = activate_code(user_id, message.text.strip())
        await message.answer(msg)

        if ok:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 بدء التخمين", callback_data="start_guess")]
            ])
            await message.answer("اضغط للبدء:", reply_markup=kb)
        return

    await message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())

@dp.callback_query(lambda c: c.data == "start_guess")
async def start_guess(callback: CallbackQuery):
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rank_"))
async def choose_rank(callback: CallbackQuery):
    user_id = callback.from_user.id
    rank = callback.data.split("_")[1]

    user_temp[user_id] = {"rank": rank}
    await callback.message.answer("اختر النوع:", reply_markup=suits_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def choose_suit(callback: CallbackQuery):
    user_id = callback.from_user.id
    suit = callback.data.split("_")[1]

    user_temp[user_id]["suit"] = suit

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    trained, last_hand = cursor.fetchone()

    if trained < 3:
        await callback.message.answer(f"⚠️ تدريب {trained+1}/3\nشنو كانت ضربتك؟", reply_markup=hands_keyboard())
    else:
        prediction = predict_hand(user_temp[user_id]["rank"], suit, last_hand)
        await callback.message.answer(f"🤖 تخميني:\n{prediction}")
        await callback.message.answer("شنو كانت ضربتك؟", reply_markup=hands_keyboard())

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hand_"))
async def choose_hand(callback: CallbackQuery):
    user_id = callback.from_user.id
    current_hand = callback.data.replace("hand_", "")

    data = user_temp.get(user_id)
    if not data:
        await callback.answer()
        return

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    trained, previous_hand = cursor.fetchone()

    save_game(data["rank"], data["suit"], previous_hand, current_hand)

    trained += 1

    cursor.execute("""
    UPDATE users SET trained_rounds=?, last_hand=?
    WHERE user_id=?
    """, (trained, current_hand, user_id))
    conn.commit()

    user_temp.pop(user_id, None)

    await callback.message.answer("✅ تم حفظ الجولة\n\nاختر رقم جديد:")
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_keyboard())
    await callback.answer()

# ================== RUN ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
