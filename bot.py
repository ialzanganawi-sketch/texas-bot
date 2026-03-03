import asyncio
import logging
import random
import string
import json
from datetime import datetime, timedelta
from collections import defaultdict

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================

API_TOKEN = "8664632562:AAHD6xaPk01W7cfX1zADS8hRwh-mfVW7s4k"
ADMIN_ID = 7717061636  # ضع ايديك هنا

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

DATA_FILE = "training_data.json"
CODES_FILE = "codes.json"
USERS_FILE = "users.json"

user_temp = {}
AI_MEMORY = []

# ================= STORAGE =================

def load_json(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

users = load_json(USERS_FILE)
codes = load_json(CODES_FILE)

def load_training():
    global AI_MEMORY
    try:
        with open(DATA_FILE, "r") as f:
            AI_MEMORY = json.load(f)
    except:
        AI_MEMORY = []

def save_training():
    with open(DATA_FILE, "w") as f:
        json.dump(AI_MEMORY, f)

# حفظ تلقائي كل 5 دقائق
async def auto_save():
    while True:
        await asyncio.sleep(300)
        save_training()

# ================= AI ENGINE =================

def ai_ready():
    return len(AI_MEMORY) >= 20

def train_ai(rank, suit, prev, curr):
    AI_MEMORY.insert(0, {
        "rank": rank,
        "suit": suit,
        "prev": prev,
        "curr": curr,
        "time": datetime.now().isoformat()
    })

def predict_hand(rank, suit, last_hand=None):

    if not ai_ready():
        return "🧠 الذكاء يحتاج 20 جولة تدريب من الادمن."

    hands = ["👥 زوجين", "🔗 متتالية", "🎴 ثلاثة", "🏠 فل هاوس", "🂡 أربعة"]
    scores = {h: 5 for h in hands}

    now = datetime.now()

    for item in AI_MEMORY[:300]:

        created = datetime.fromisoformat(item["time"])
        days_old = (now - created).days

        if days_old <= 3:
            time_weight = 4
        elif days_old <= 7:
            time_weight = 2
        else:
            time_weight = 1

        if item["rank"] == rank and item["suit"] == suit:
            scores[item["curr"]] += 6 * time_weight

        if last_hand and item["prev"] == last_hand:
            scores[item["curr"]] += 4 * time_weight

        scores[item["curr"]] += 1

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
        f"🎯 TEXAS AI V8 ULTRA\n\n"
        f"🔥 عالي:\n{high[0]} ({high[1]}%)\n\n"
        f"⚖️ متوسط:\n{mid[0]} ({mid[1]}%)\n\n"
        f"⚠️ منخفض:\n{low[0]} ({low[1]}%)"
    )

# ================= SUBSCRIPTION =================

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def check_subscription(user_id):
    if str(user_id) not in users:
        return False
    return datetime.fromisoformat(users[str(user_id)]) > datetime.now()

def activate_code(user_id, code):
    if code not in codes:
        return False, "❌ الكود غير موجود"
    if codes[code]["used"]:
        return False, "❌ الكود مستخدم"

    expire = datetime.now() + timedelta(days=codes[code]["days"])
    users[str(user_id)] = expire.isoformat()
    codes[code]["used"] = True

    save_json(USERS_FILE, users)
    save_json(CODES_FILE, codes)

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

    days = int(message.text.split()[1]) if len(message.text.split()) > 1 else 7
    code = generate_code()

    codes[code] = {"used": False, "days": days}
    save_json(CODES_FILE, codes)

    await message.answer(f"كود جديد:\n`{code}`\nالمدة: {days} يوم", parse_mode="Markdown")

@dp.message(Command("train"))
async def train(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    user_temp[message.from_user.id] = {"mode": "train"}
    await message.answer("اختر رقم الورقة:", reply_markup=ranks_kb())

# ================= FLOW =================

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("🔥 TEXAS AI V8\nادخل كود الاشتراك")

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

@dp.callback_query(lambda c: c.data.startswith("suit_"))
async def choose_suit(callback: CallbackQuery):
    user_temp[callback.from_user.id]["suit"] = callback.data.split("_")[1]
    await callback.message.edit_text("الضربة السابقة؟ (اختياري)", reply_markup=hands_kb(optional=True))

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

@dp.callback_query(lambda c: True)
async def train_result(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_temp.get(user_id)

    if user_id == ADMIN_ID and data and data.get("mode") == "train_result":
        curr = callback.data.replace("hand_", "")
        train_ai(data["rank"], data["suit"], data["prev"], curr)
        await callback.message.edit_text("✅ تم حفظ التدريب\nالذكاء يزيد يومياً 🔥")
        user_temp.pop(user_id, None)

# ================= RUN =================

async def main():
    logging.basicConfig(level=logging.INFO)
    load_training()
    asyncio.create_task(auto_save())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
