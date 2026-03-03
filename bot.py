import sqlite3
import asyncio
import logging
import random
import string
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================

API_TOKEN = "8664632562:AAGktBos2yPZ0-zBXKsE0CRGr1G8XoGUeEo"
ADMIN_ID = 7717061636  # ضع ايديك هنا

DB_PATH = "texas_v6.db"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_temp = {}

# ================= DATABASE =================

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    subscription_until TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS codes(
    code TEXT PRIMARY KEY,
    is_used INTEGER DEFAULT 0,
    used_by INTEGER,
    duration_days INTEGER,
    created_at TEXT
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

# ================= AI CACHE =================

AI_CACHE = []
MAX_CACHE = 300

def load_training():
    global AI_CACHE
    cursor.execute("""
    SELECT rank, suit, previous_hand, current_hand
    FROM games
    ORDER BY created_at DESC
    LIMIT 300
    """)
    AI_CACHE = cursor.fetchall()

def train_ai(rank, suit, prev, curr):
    global AI_CACHE
    cursor.execute("""
    INSERT INTO games(rank, suit, previous_hand, current_hand, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (rank, suit, prev, curr, datetime.now().isoformat()))
    conn.commit()

    AI_CACHE.insert(0, (rank, suit, prev, curr))
    if len(AI_CACHE) > MAX_CACHE:
        AI_CACHE.pop()

def predict_hand(rank, suit, last_hand=None):
    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]

    if not AI_CACHE:
        load_training()

    scores = defaultdict(lambda: 3)

    for r, s, prev, curr in AI_CACHE:

        if r == rank and s == suit:
            scores[curr] += 8

        if last_hand and prev == last_hand:
            scores[curr] += 6

        scores[curr] += 1

    recent = AI_CACHE[:30]
    streak = defaultdict(int)

    for _, _, _, curr in recent:
        streak[curr] += 1

    for hand, count in streak.items():
        if count >= 3:
            scores[hand] += 7

    total = sum(scores[h] for h in hands)

    percentages = {
        h: round((scores[h] / total) * 100, 1)
        for h in hands
    }

    sorted_hands = sorted(percentages.items(), key=lambda x: x[1], reverse=True)

    high = sorted_hands[0]
    mid = sorted_hands[1]
    low = sorted_hands[-1]

    return (
        f"🎯 TEXAS AI V6\n\n"
        f"🔥 عالي:\n{high[0]} ({high[1]}%)\n\n"
        f"⚖️ متوسط:\n{mid[0]} ({mid[1]}%)\n\n"
        f"⚠️ منخفض:\n{low[0]} ({low[1]}%)"
    )

# ================= SUBSCRIPTION =================

def generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def check_subscription(user_id):
    cursor.execute("SELECT subscription_until FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    return datetime.fromisoformat(row[0]) > datetime.now()

def activate_code(user_id, code):
    cursor.execute("SELECT is_used, duration_days FROM codes WHERE code=?", (code,))
    row = cursor.fetchone()

    if not row:
        return False, "❌ الكود غير موجود"
    if row[0] == 1:
        return False, "❌ الكود مستخدم"

    expire = datetime.now() + timedelta(days=row[1])

    cursor.execute("INSERT OR REPLACE INTO users(user_id, subscription_until) VALUES(?,?)",
                   (user_id, expire.isoformat()))

    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE code=?",
                   (user_id, code))
    conn.commit()

    return True, "✅ تم تفعيل الاشتراك"

# ================= KEYBOARDS =================

def ranks_kb():
    ranks = ["A","K","Q","J","10","9","8","7","6","5","4","3","2"]
    rows = [ranks[i:i+4] for i in range(0,len(ranks),4)]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=r, callback_data=f"rank_{r}") for r in row]
            for row in rows
        ]
    )

def suits_kb():
    suits = ["♥️","♦️","♣️","♠️"]
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=s, callback_data=f"suit_{s}") for s in suits]]
    )

def hands_kb(optional=False):
    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    kb = [[InlineKeyboardButton(text=h, callback_data=f"hand_{h}")] for h in hands]
    if optional:
        kb.append([InlineKeyboardButton(text="بدون", callback_data="hand_none")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ================= ADMIN =================

@dp.message(Command("addcode"))
async def add_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    days = int(parts[1]) if len(parts) > 1 else 7

    code = generate_code()

    cursor.execute("""
    INSERT INTO codes(code, is_used, used_by, duration_days, created_at)
    VALUES (?,0,NULL,?,?)
    """, (code, days, datetime.now().isoformat()))
    conn.commit()

    await message.answer(f"كود جديد:\n`{code}`\nالمدة: {days} يوم", parse_mode="Markdown")

@dp.message(Command("train"))
async def admin_train(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("اختر رقم الورقة للتدريب:", reply_markup=ranks_kb())
    user_temp[message.from_user.id] = {"mode": "train"}

# ================= FLOW =================

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 إدخال كود", callback_data="enter")]
    ])
    await message.answer("🔥 TEXAS AI V6\nادخل كود الاشتراك", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "enter")
async def enter(callback: CallbackQuery):
    await callback.message.answer("ارسل الكود:")
    await callback.answer()

@dp.message()
async def handle_text(message: Message):
    if not check_subscription(message.from_user.id):
        ok, msg = activate_code(message.from_user.id, message.text.strip())
        await message.answer(msg)
        return

    await message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())

@dp.callback_query(lambda c: c.data.startswith("rank_"))
async def choose_rank(callback: CallbackQuery):
    user_temp[callback.from_user.id] = user_temp.get(callback.from_user.id, {})
    user_temp[callback.from_user.id]["rank"] = callback.data.split("_")[1]
    await callback.message.answer("اختر النوع:", reply_markup=suits_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def choose_suit(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_temp[user_id]["suit"] = callback.data.split("_")[1]
    await callback.message.answer("الضربة السابقة؟ (اختياري)", reply_markup=hands_kb(optional=True))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hand_"))
async def choose_hand(callback: CallbackQuery):
    user_id = callback.from_user.id
    prev = callback.data.replace("hand_", "")
    if prev == "none":
        prev = None

    data = user_temp.get(user_id)
    if not data:
        return

    rank = data["rank"]
    suit = data["suit"]

    if user_id == ADMIN_ID and data.get("mode") == "train":
        await callback.message.answer("شنو كانت النتيجة الفعلية؟", reply_markup=hands_kb())
        user_temp[user_id]["prev"] = prev
        user_temp[user_id]["mode"] = "train_result"
        return

    result = predict_hand(rank, suit, prev)
    await callback.message.answer(result)
    user_temp.pop(user_id, None)
    await callback.answer()

@dp.callback_query(lambda c: True)
async def train_result(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_temp.get(user_id)

    if user_id == ADMIN_ID and data and data.get("mode") == "train_result":
        curr = callback.data.replace("hand_", "")
        train_ai(data["rank"], data["suit"], data["prev"], curr)
        await callback.message.answer("✅ تم تدريب الذكاء")
        user_temp.pop(user_id, None)

# ================= RUN =================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    load_training()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
