# =======================================================
#  الكود النهائي المطلوب - نسخة 2025/2026
# =======================================================

import os
import logging
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# إعدادات
# ────────────────────────────────────────────────

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN غير موجود!")

ACTIVATION_CODE = "SECRET123"           # ← غيّر الكود

SA_TZ = ZoneInfo("Asia/Riyadh")

# حالات المحادثة
CHOOSING, PREDICT_HAND, PREDICT_SUIT, PREDICT_RANK, ASK_ACTUAL_HIT = range(5)

HAND_OPTIONS = [
    ["زوج", "زوجين", "دبل AA"],
    ["ثلاثة", "أربعة"],
    ["فل هاوس", "متتالية"],
    ["متتالية نوع واحد", "رويال"],
    ["↩️ إلغاء"]
]

SUIT_EMOJIS = ["♥️", "♦️", "♣️", "♠️", "↩️ رجوع"]

RANK_OPTIONS = [
    ["2", "3", "4", "5"],
    ["6", "7", "8", "9"],
    ["10", "J", "Q", "K", "A"],
    ["↩️ رجوع"]
]

# ────────────────────────────────────────────────
# دوال مساعدة
# ────────────────────────────────────────────────

def is_activated(context, user_id: int) -> bool:
    return user_id in context.application.bot_data.get("activated", {})

def activate_user(context, user_id: int, choice: str):
    activated = context.application.bot_data.setdefault("activated", {})
    activated[user_id] = choice

# ────────────────────────────────────────────────
# توليد توقعات أسماء + تقدير زمني
# ────────────────────────────────────────────────

def generate_name_predictions(last_hand: str, recent_hands: list) -> list:
    """ترجع قائمة توقعات مرتبة حسب الاحتمال التقريبي"""
    base = []

    if any(w in last_hand for w in ["أربع", "رويال"]):
        base = ["زوج", "زوجين", "ثلاثة", "فل هاوس"]
    elif "فل هاوس" in last_hand:
        base = ["أربعة", "ثلاثة", "زوجين", "متتالية نوع واحد"]
    elif any(w in last_hand for w in ["ثلاث", "ثلاثة"]):
        base = ["زوجين", "فل هاوس", "أربعة", "متتالية"]
    elif any(w in last_hand for w in ["زوج", "دبل"]):
        base = ["ثلاثة", "زوجين", "فل هاوس", "أربعة"]
    elif "متتالية" in last_hand:
        base = ["متتالية نوع واحد", "فل هاوس", "ثلاثة", "زوجين"]
    else:
        base = ["زوجين", "ثلاثة", "فل هاوس", "أربعة"]

    # خلط خفيف + أخذ أول 3–4
    random.shuffle(base)
    return base[:4]


def estimate_next_times(last_hit_time: datetime = None) -> str:
    """تقدير زمني بسيط (دقايق بعد)"""
    now = datetime.now(SA_TZ)

    if last_hit_time is None:
        last_hit_time = now - timedelta(minutes=random.randint(2, 12))

    minutes_ago = (now - last_hit_time).total_seconds() / 60

    if minutes_ago < 3:
        return "ممكن خلال 2–6 دقايق"
    elif minutes_ago < 8:
        return "غالباً خلال 4–11 دقيقة"
    elif minutes_ago < 15:
        return "متوقع خلال 7–16 دقيقة"
    else:
        return "يمكن يجي خلال 5–20 دقيقة (اللعبة باردة شوي)"


# ────────────────────────────────────────────────
# Handlers
# ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = [["ربح متزايد"], ["بس أربعة"], ["بس دبل AA"], ["دبل AA وأربعة"]]
    await update.message.reply_text(
        "مرحبا! 🚀\nاختر نوع الخدمة:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return CHOOSING


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    valid = ["ربح متزايد", "بس أربعة", "بس دبل AA", "دبل AA وأربعة"]

    if text not in valid:
        await update.message.reply_text("اختار من الأزرار")
        return CHOOSING

    context.user_data["choice"] = text

    msg = f"اختيارك: *{text}*\n\n"
    if text == "ربح متزايد":
        msg += f"للتفعيل أرسل:\n`/activate {ACTIVATION_CODE}`"
    else:
        msg += "تواصل معي للدفع"

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] != ACTIVATION_CODE:
        await update.message.reply_text(f"كود خاطئ! استخدم /activate {ACTIVATION_CODE}")
        return

    uid = update.effective_user.id
    choice = context.user_data.get("choice")

    if not choice:
        await update.message.reply_text("اختار النوع أولاً من /start")
        return

    if is_activated(context, uid):
        await update.message.reply_text("حسابك مفعّل مسبقاً")
        return

    activate_user(context, uid, choice)

    await update.message.reply
