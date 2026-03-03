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

API_TOKEN = "8664632562:AAH9KQRkNDI9h6pVy3t6VFhitIrHCcyi-V8"
ADMIN_ID = 7717061636  # ضع الايدي مالك

DB_PATH = "texas_ai_v4.db"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
user_temp = {}

# ================== DATABASE ==================

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

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
    duration_days INTEGER
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

HANDS = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]

# ================== HELPERS ==================

def generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def check_subscription(user_id):
    cursor.execute("SELECT subscription_until FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return False
    return datetime.fromisoformat(row[0]) > datetime.now()

def activate_code(user_id, code):
    cursor.execute("SELECT is_used, duration_days FROM codes WHERE code=?", (code,))
    row = cursor.fetchone()

    if not row:
        return False, "❌ الكود غير موجود"
    if row[0] == 1:
        return False, "❌ الكود مستخدم سابقاً"

    duration = row[1]
    expire_date = datetime.now() + timedelta(days=duration)

    cursor.execute("""
    INSERT OR REPLACE INTO users(user_id, subscription_until, trained_rounds, last_hand)
    VALUES(?, ?, 0, NULL)
    """, (user_id, expire_date.isoformat()))

    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE code=?", (user_id, code))
    conn.commit()

    return True, f"✅ تم تفعيل الاشتراك لمدة {duration} يوم"

def save_game(rank, suit, previous_hand, current_hand):
    cursor.execute("""
    INSERT INTO games(rank, suit, previous_hand, current_hand, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (rank, suit, previous_hand, current_hand, datetime.now().isoformat()))
    conn.commit()

# ================== SMART AI ==================

def predict_hand(rank, suit, last_hand):
    # --- 1) احصائيات حسب الرتبة + النوع
    cursor.execute("""
    SELECT current_hand, COUNT(*) 
    FROM games
    WHERE rank=? AND suit=?
    GROUP BY current_hand
    """, (rank, suit))
    rs_data = dict(cursor.fetchall())

    # --- 2) احصائيات انتقال من الضربة السابقة (Markov)
    markov_data = {}
    if last_hand:
        cursor.execute("""
        SELECT current_hand, COUNT(*)
        FROM games
        WHERE previous_hand=?
        GROUP BY current_hand
        """, (last_hand,))
        markov_data = dict(cursor.fetchall())

    scores = {}

    for h in HANDS:
        rs_score = rs_data.get(h, 0)
        mk_score = markov_data.get(h, 0)

        # وزن 60% rank+suit ، 40% انتقال
        score = (rs_score * 0.6) + (mk_score * 0.4)
        scores[h] = score

    if all(v == 0 for v in scores.values()):
        return random.choice(HANDS), 0

    prediction = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = int((scores[prediction] / total) * 100) if total > 0 else 0

    return prediction, confidence

# ================== KEYBOARDS ==================

def ranks_kb():
    ranks = ["A","K","Q","J","10","9","8","7","6","5","4","3","2"]
    rows = [ranks[i:i+4] for i in range(0,len(ranks),4)]
    keyboard = [[InlineKeyboardButton(text=r, callback_data=f"rank_{r}") for r in row] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def suits_kb():
    suits = ["♥️","♦️","♣️","♠️"]
    keyboard = [[InlineKeyboardButton(text=s, callback_data=f"suit_{s}") for s in suits]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def hands_kb():
    keyboard = [[InlineKeyboardButton(text=h, callback_data=f"hand_{h}")] for h in HANDS]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================== ADMIN ==================

@dp.message(Command("addcode"))
async def add_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("غير مصرح ❌")
        return

    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 else 7
    code = generate_code()

    cursor.execute("""
    INSERT INTO codes(code, is_used, created_at, duration_days)
    VALUES(?, 0, ?, ?)
    """, (code, datetime.now().isoformat(), days))
    conn.commit()

    await message.answer(f"✅ كود:\n`{code}`\nمدة: {days} يوم", parse_mode="Markdown")

# ================== START ==================

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 إدخال الكود", callback_data="enter")]
    ])
    await message.answer("🔥 Texas AI V4\nادخل الكود لتفعيل الاشتراك", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "enter")
async def enter(callback: CallbackQuery):
    await callback.message.answer("📩 ارسل الكود الآن:")
    await callback.answer()

@dp.message()
async def handle_text(message: Message):
    user_id = message.from_user.id

    if not check_subscription(user_id):
        ok, msg = activate_code(user_id, message.text.strip())
        await message.answer(msg)

        if ok:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 بدء التخمين", callback_data="start_guess")]
            ])
            await message.answer("اضغط لبدء التخمين:", reply_markup=kb)
        return

    await message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())

@dp.callback_query(lambda c: c.data == "start_guess")
async def start_guess(callback: CallbackQuery):
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rank_"))
async def rank(callback: CallbackQuery):
    user_id = callback.from_user.id
    r = callback.data.split("_")[1]
    user_temp[user_id] = {"rank": r}
    await callback.message.answer("اختر النوع:", reply_markup=suits_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def suit(callback: CallbackQuery):
    user_id = callback.from_user.id
    s = callback.data.split("_")[1]
    user_temp[user_id]["suit"] = s

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    trained, last_hand = cursor.fetchone()

    if trained < 3:
        await callback.message.answer(f"⚠️ تدريب {trained+1}/3\nشنو كانت ضربتك؟", reply_markup=hands_kb())
    else:
        prediction, confidence = predict_hand(user_temp[user_id]["rank"], s, last_hand)
        await callback.message.answer(f"🤖 تخميني: {prediction}\n📊 نسبة الثقة: {confidence}%")
        await callback.message.answer("شنو كانت ضربتك؟", reply_markup=hands_kb())

    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hand_"))
async def hand(callback: CallbackQuery):
    user_id = callback.from_user.id
    current = callback.data.replace("hand_", "")

    data = user_temp.get(user_id)
    if not data:
        await callback.answer()
        return

    cursor.execute("SELECT trained_rounds, last_hand FROM users WHERE user_id=?", (user_id,))
    trained, previous = cursor.fetchone()

    save_game(data["rank"], data["suit"], previous, current)

    trained += 1
    cursor.execute("UPDATE users SET trained_rounds=?, last_hand=? WHERE user_id=?", (trained, current, user_id))
    conn.commit()

    user_temp.pop(user_id, None)

    await callback.message.answer("✅ تم حفظ الجولة\n\nاختر رقم جديد:")
    await callback.message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())
    await callback.answer()

# ================== RUN ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
