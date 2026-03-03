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
# إعدادات أساسية
# ────────────────────────────────────────────────

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN غير موجود في Environment Variables")

ACTIVATION_CODE = "SECRET123"  # غيّره لاحقاً إلى كود قوي

SA_TZ = ZoneInfo("Asia/Riyadh")

# حالات المحادثة
CHOOSING = 0
PREDICT = 1

# خيارات الأزرار
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

def get_prediction(last_hand: str, recent_mults: list) -> float:
    if not recent_mults:
        return round(random.uniform(1.7, 4.2), 2)

    avg = sum(recent_mults) / len(recent_mults)

    if any(word in last_hand.lower() for word in ["أربع", "رويال", "فل"]):
        return round(random.uniform(1.3, 2.6), 2)

    if len(recent_mults) >= 3 and all(m >= 3.5 for m in recent_mults[-3:]):
        return round(random.uniform(1.4, 2.3), 2)

    if any(word in last_hand.lower() for word in ["زوج", "دبل", "ثلاث"]):
        return round(random.uniform(avg * 0.9, avg * 1.45), 2)

    return round(random.uniform(1.9, 4.0), 2)

# ────────────────────────────────────────────────
# إرسال تحديثات دورية
# ────────────────────────────────────────────────

async def send_update(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(SA_TZ).strftime("%H:%M")
    msg = f"تحديث {now} – أوقات مقترحة (مثال):\n" + "\n".join([f"• {t:02d}:{m:02d}" for t, m in [(now.split(':')[0], (int(now.split(':')[1]) + i*2 + 3) % 60) for i in range(1,6)]])

    activated = context.application.bot_data.get("activated", {})
    for uid, ch in activated.items():
        if ch == "ربح متزايد":
            try:
                await context.bot.send_message(uid, msg)
            except:
                pass

# ────────────────────────────────────────────────
# Handlers
# ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["ربح متزايد"],
        ["بس أربعة"],
        ["بس دبل AA"],
        ["دبل AA وأربعة"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "مرحبا! 🚀\nاختر نوع الخدمة:",
        reply_markup=reply_markup
    )
    return CHOOSING


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    valid_choices = ["ربح متزايد", "بس أربعة", "بس دبل AA", "دبل AA وأربعة"]

    if text not in valid_choices:
        await update.message.reply_text("اختار من الأزرار لو سمحت")
        return CHOOSING

    context.user_data["choice"] = text

    msg = f"اختيارك: *{text}*\n\n"
    if text == "ربح متزايد":
        msg += f"للتفعيل أرسل:\n`/activate {ACTIVATION_CODE}`"
    else:
        msg += "تواصل معي للدفع: @YourUsername"

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] != ACTIVATION_CODE:
        await update.message.reply_text(f"كود خاطئ! استخدم: /activate {ACTIVATION_CODE}")
        return

    user_id = update.effective_user.id
    choice = context.user_data.get("choice")

    if not choice:
        await update.message.reply_text("اختار نوع الخدمة أولاً من /start")
        return

    if is_activated(context, user_id):
        await update.message.reply_text("حسابك مفعّل مسبقاً")
        return

    activate_user(context, user_id, choice)

    await update.message.reply_text(
        f"تم التفعيل ✅\n"
        f"النوع: {choice}\n\n"
        "متاح لك الآن:\n"
        "/predict  ← خمن الضربة\n"
        "أرسل x2.5 ← سجّل النتيجة"
    )


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_activated(context, update.effective_user.id):
        await update.message.reply_text("يجب التفعيل أولاً → /start ثم /activate")
        return ConversationHandler.END

    keyboard = []
    for row in HAND_OPTIONS:
        keyboard.append([InlineKeyboardButton(txt, callback_data=f"hand_{txt}") for txt in row])

    await update.message.reply_text(
        "اختر **آخر ضربة** حصلت:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PREDICT


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("hand_"):
        hand = data[5:]
        if hand == "↩️ إلغاء":
            await query.edit_message_text("تم الإلغاء.")
            return ConversationHandler.END

        context.user_data["last_hand"] = hand

        keyboard = [[InlineKeyboardButton(emoji, callback_data=f"suit_{emoji}")] for emoji in SUIT_EMOJIS]
        await query.edit_message_text(
            f"آخر ضربة: {hand}\n\nاختر نوع آخر ورقة (إيموجي):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PREDICT

    elif data.startswith("suit_"):
        suit = data[5:]
        if suit == "↩️ رجوع":
            keyboard = []
            for row in HAND_OPTIONS:
                keyboard.append([InlineKeyboardButton(txt, callback_data=f"hand_{txt}") for txt in row])
            await query.edit_message_text("اختر آخر ضربة حصلت:", reply_markup=InlineKeyboardMarkup(keyboard))
            return PREDICT

        context.user_data["last_suit"] = suit

        keyboard = []
        for row in RANK_OPTIONS:
            keyboard.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in row])

        await query.edit_message_text(
            f"آخر ضربة: {context.user_data.get('last_hand')}\n"
            f"نوع الورقة: {suit}\n\n"
            "اختر قيمة آخر ورقة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PREDICT

    elif data.startswith("rank_"):
        rank = data[5:]
        if rank == "↩️ رجوع":
            keyboard = [[InlineKeyboardButton(e, callback_data=f"suit_{e}")] for e in SUIT_EMOJIS]
            await query.edit_message_text("اختر نوع آخر ورقة:", reply_markup=InlineKeyboardMarkup(keyboard))
            return PREDICT

        last_hand = context.user_data.get("last_hand", "غير معروف")
        last_suit = context.user_data.get("last_suit", "?")
        last_rank = rank

        user_hist = context.application.bot_data.setdefault("pred_hist", {}).setdefault(update.effective_user.id, deque(maxlen=12))
        recent = [m for _, m in user_hist]

        pred = get_prediction(last_hand, recent)

        text = (
            f"**الحالة المختارة:**\n"
            f"• آخر ضربة: {last_hand}\n"
            f"• آخر ورقة: {last_rank} {last_suit}\n\n"
            f"التنبؤ القادم: **x{pred:.2f}** ±0.8\n\n"
            "بعد النتيجة أرسل: x3.1"
        )

        await query.edit_message_text(text)

        context.user_data["pending_pred"] = pred
        context.user_data["pending_hand"] = last_hand

        return ConversationHandler.END

    return ConversationHandler.END


async def save_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip().lower()
    if not text.startswith("x") or len(text) < 2:
        return

    try:
        val = float(text[1:])
    except ValueError:
        await update.message.reply_text("صيغة خاطئة → مثال: x2.8")
        return

    pred = context.user_data.pop("pending_pred", None)
    hand = context.user_data.pop("pending_hand", None)

    if pred is None or hand is None:
        return

    uid = update.effective_user.id
    hist = context.application.bot_data.setdefault("pred_hist", {}).setdefault(uid, deque(maxlen=12))
    hist.append((hand, val))

    diff = abs(pred - val)
    await update.message.reply_text(
        f"تم حفظ: {text}\n"
        f"التنبؤ كان: x{pred:.2f}\n"
        f"الفرق: ±{diff:.2f}"
    )


def main():
    print("جاري تشغيل البوت...")

    app = Application.builder().token(TOKEN).build()
    print("Application تم إنشاؤها")

    conv_choice = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]},
        fallbacks=[],
    )

    conv_predict = ConversationHandler(
        entry_points=[CommandHandler("predict", cmd_predict)],
        states={PREDICT: [CallbackQueryHandler(button_handler)]},
        fallbacks=[],
    )

    app.add_handler(conv_choice)
    app.add_handler(conv_predict)
    app.add_handler(MessageHandler(filters.Regex(r'^x[\d.]+$'), save_result))
    app.add_handler(CommandHandler("activate", activate))

    app.job_queue.run_repeating(send_update, interval=600, first=30)

    print("بدء polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
