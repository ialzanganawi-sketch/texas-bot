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

# ================== CONFIG ==================

API_TOKEN = "8664632562:AAEhHhz2kudRdtjAs5z2s29Ui31pyrl92EU"
ADMIN_ID = 7717061636  # حط ايديك هنا
DB_PATH = "texas_v7.db"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_temp = {}

# ================== DATABASE ==================

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

# ================== AI ==================

def ai_ready():
    cursor.execute("SELECT COUNT(*) FROM games")
    return cursor.fetchone()[0] >= 20


def train_ai(rank, suit, prev, curr):
    cursor.execute("""
    INSERT INTO games(rank, suit, previous_hand, current_hand, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (rank, suit, prev, curr, datetime.now().isoformat()))
    conn.commit()


def predict_hand(rank, suit, last_hand=None):
    if not ai_ready():
        return "🧠 الذكاء غير مكتمل.\nلازم 20 جولة تدريب من الادمن."

    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    scores = {h: 5 for h in hands}

    cursor.execute("""
    SELECT rank, suit, previous_hand, current_hand, created_at
    FROM games
    ORDER BY created_at DESC
    LIMIT 300
    """)
    rows = cursor.fetchall()

    now = datetime.now()

    for r, s, prev, curr, created in rows:
        created_time = datetime.fromisoformat(created)
        days_old = (now - created_time).days

        if days_old <= 3:
            time_weight = 4
        elif days_old <= 7:
            time_weight = 2
        else:
            time_weight = 1

        if r == rank and s == suit:
            scores[curr] += 6 * time_weight

        if last_hand and prev == last_hand:
            scores[curr] += 4 * time_weight

        scores[curr] += 1

    total = sum(scores.values())

    percentages = {
        h: round((scores[h] / total) * 100, 1)
        for h in hands
    }

    sorted_hands = sorted(percentages.items(), key=lambda x: x[1], reverse=True)

    high = sorted_hands[0]
    mid = sorted_hands[1]
    low = sorted_hands[-1]

    return (
        f"🎯 TEXAS AI V7 PRO\n\n"
        f"🔥 عالي:\n{high[0]} ({high[1]}%)\n\n"
        f"⚖️ متوسط:\n{mid[0]} ({mid[1]}%)\n\n"
        f"⚠️ منخفض:\n{low[0]} ({low[1]}%)"
    )

# ================== SUBSCRIPTION ==================

def generate_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


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

    cursor.execute("INSERT OR REPLACE INTO users VALUES(?,?)",
                   (user_id, expire.isoformat()))
    cursor.execute("UPDATE codes SET is_used=1, used_by=? WHERE code=?",
                   (user_id, code))
    conn.commit()

    return True, "✅ تم تفعيل الاشتراك"

# ================== KEYBOARDS ==================

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

# ================== ADMIN ==================

@dp.message(Command("addcode"))
async def add_code(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    days = int(message.text.split()[1]) if len(message.text.split()) > 1 else 7
    code = generate_code()

    cursor.execute("INSERT INTO codes VALUES(?,?,?,?,?)",
                   (code,0,None,days,datetime.now().isoformat()))
    conn.commit()

    await message.answer(f"كود جديد:\n`{code}`\nالمدة: {days} يوم", parse_mode="Markdown")

@dp.message(Command("train"))
async def admin_train(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    user_temp[message.from_user.id] = {"mode": "train"}
    await message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())

# ================== FLOW ==================

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 إدخال كود", callback_data="enter")]
    ])
    await message.answer("🔥 TEXAS AI V7 PRO", reply_markup=kb)

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
    await callback.message.edit_text("اختر النوع:", reply_markup=suits_kb())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def choose_suit(callback: CallbackQuery):
    user_temp[callback.from_user.id]["suit"] = callback.data.split("_")[1]
    await callback.message.edit_text("الضربة السابقة؟ (اختياري)", reply_markup=hands_kb(optional=True))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("hand_"))
async def choose_hand(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_temp.get(user_id)
    if not data:
        return

    prev = callback.data.replace("hand_", "")
    if prev == "none":
        prev = None

    rank = data["rank"]
    suit = data["suit"]

    if user_id == ADMIN_ID and data.get("mode") == "train":
        user_temp[user_id]["prev"] = prev
        user_temp[user_id]["mode"] = "train_result"
        await callback.message.edit_text("شنو كانت النتيجة الفعلية؟", reply_markup=hands_kb())
        return

    result = predict_hand(rank, suit, prev)
    await callback.message.edit_text(result)
    user_temp.pop(user_id, None)
    await callback.answer()

@dp.callback_query(lambda c: True)
async def train_result(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_temp.get(user_id)

    if user_id == ADMIN_ID and data and data.get("mode") == "train_result":
        curr = callback.data.replace("hand_", "")
        train_ai(data["rank"], data["suit"], data["prev"], curr)
        await callback.message.edit_text("✅ تم حفظ التدريب\nالجولات الحالية تتحدث يومياً")
        user_temp.pop(user_id, None)

# ================== RUN ==================

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
