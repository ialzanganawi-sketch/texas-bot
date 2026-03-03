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

ACTIVATION_CODE = "SECRET123"  # ← غيّره إلى كود قوي

SA_TZ = ZoneInfo("Asia/Riyadh")

# حالات المحادثة
CHOOSING, PREDICT_HAND, PREDICT_SUIT, PREDICT_RANK, ASK_ACTUAL_HIT = range(5)

# الخانة القوية منفصلة في الأعلى
STRONG_HAND = "أربعة أو أقوى"

HAND_OPTIONS_NORMAL = [
    ["زوج", "زوجين", "دبل AA"],
    ["ثلاثة", "ثلاثية"],
    ["فل هاوس", "متتالية", "متتالية نوع واحد"],
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

def generate_name_predictions(last_hand: str) -> list:
    last_lower = last_hand.lower()

    # بعد "أربعة أو أقوى" → توقع محافظ + تحذير
    if "أربع" in last_lower or "أقوى" in last_lower:
        return [
            "زوج",
            "زوجين",
            "ثلاثة",
            "احتمال crash عالي بعد هالضربة"
        ]

    # حالات عادية
    if "فل هاوس" in last_lower:
        return ["أربعة أو أقوى", "ثلاثية", "زوجين", "متتالية نوع واحد"]

    if "ثلاث" in last_lower:
        return ["زوجين", "فل هاوس", "أربعة أو أقوى", "متتالية"]

    if "زوج" in last_lower or "دبل" in last_lower:
        return ["ثلاثة", "زوجين", "فل هاوس", "أربعة أو أقوى"]

    if "متتالية" in last_lower:
        return ["متتالية نوع واحد", "فل هاوس", "ثلاثية", "أربعة أو أقوى"]

    # افتراضي
    return ["زوجين", "ثلاثة", "فل هاوس", "أربعة أو أقوى"]

# ────────────────────────────────────────────────
# التحديث الدوري
# ────────────────────────────────────────────────

async def send_update(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(SA_TZ).strftime("%H:%M")
    msg = f"تحديث {now} – أوقات مقترحة (مثال):\n" + "\n".join([f"• {i:02d}:{(j*4)%60:02d}" for i,j in enumerate(range(5),1)])

    activated = context.application.bot_data.get("activated", {})
    for uid, ch in activated.items():
        if ch == "ربح متزايد":
            try:
                await context.bot.send_message(uid, msg)
            except Exception:
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
    await update.message.reply_text(
        "مرحبا! 🚀\nاختر نوع الخدمة:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
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
        msg += "تواصل معي للدفع: @YourUsername"

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] != ACTIVATION_CODE:
        await update.message.reply_text(f"كود خاطئ → /activate {ACTIVATION_CODE}")
        return

    uid = update.effective_user.id
    choice = context.user_data.get("choice")

    if not choice:
        await update.message.reply_text("اختار من /start أولاً")
        return

    if is_activated(context, uid):
        await update.message.reply_text("مفعّل مسبقاً")
        return

    activate_user(context, uid, choice)

    await update.message.reply_text(
        f"تم التفعيل ✅\nنوع: {choice}\n\n"
        "/predict ← للتنبؤ\nx2.7 ← لحفظ نتيجة (اختياري)"
    )


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_activated(context, update.effective_user.id):
        await update.message.reply_text("يجب التفعيل أولاً → /start ثم /activate")
        return ConversationHandler.END

    keyboard = []

    # الخانة القوية منفصلة في الأعلى
    keyboard.append([InlineKeyboardButton(STRONG_HAND, callback_data=f"hand_{STRONG_HAND}")])

    # باقي الخانات العادية
    for row in HAND_OPTIONS_NORMAL:
        keyboard.append([InlineKeyboardButton(txt, callback_data=f"hand_{txt}") for txt in row])

    await update.message.reply_text(
        "اختر آخر ضربة حصلت:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PREDICT_HAND


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

        keyboard = [[InlineKeyboardButton(e, callback_data=f"suit_{e}")] for e in SUIT_EMOJIS]
        await query.edit_message_text(
            f"آخر ضربة: {hand}\n\nاختر نوع آخر ورقة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PREDICT_SUIT

    elif data.startswith("suit_"):
        suit = data[5:]
        if suit == "↩️ رجوع":
            keyboard = []
            # الخانة القوية منفصلة عند الرجوع أيضاً
            keyboard.append([InlineKeyboardButton(STRONG_HAND, callback_data=f"hand_{STRONG_HAND}")])
            for row in HAND_OPTIONS_NORMAL:
                keyboard.append([InlineKeyboardButton(txt, callback_data=f"hand_{txt}") for txt in row])
            await query.edit_message_text("اختر آخر ضربة:", reply_markup=InlineKeyboardMarkup(keyboard))
            return PREDICT_HAND

        context.user_data["last_suit"] = suit

        keyboard = []
        for row in RANK_OPTIONS:
            keyboard.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in row])

        await query.edit_message_text(
            f"آخر ضربة: {context.user_data['last_hand']}\n"
            f"نوع الورقة: {suit}\n\n"
            "اختر قيمة الورقة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PREDICT_RANK

    elif data.startswith("rank_"):
        rank = data[5:]
        if rank == "↩️ رجوع":
            keyboard = [[InlineKeyboardButton(e, callback_data=f"suit_{e}")] for e in SUIT_EMOJIS]
            await query.edit_message_text("اختر نوع الورقة:", reply_markup=InlineKeyboardMarkup(keyboard))
            return PREDICT_SUIT

        context.user_data["last_rank"] = rank

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("أرسل الضربة الفعلية", callback_data="send_hit")],
            [InlineKeyboardButton("تخطي ← تنبؤ مباشر", callback_data="skip_hit")]
        ])

        await query.edit_message_text(
            f"تم اختيار:\n"
            f"• الضربة السابقة: {context.user_data['last_hand']}\n"
            f"• الورقة: {rank} {context.user_data['last_suit']}\n\n"
            "شنو الضربة اللي ضربت فعلياً هالمرة؟\n(اختياري – لتحسين التوقعات المستقبلية)",
            reply_markup=keyboard
        )
        return ASK_ACTUAL_HIT

    elif data in ("send_hit", "skip_hit"):
        if data == "skip_hit":
            await do_final_prediction(query, context)
            return ConversationHandler.END

        await query.edit_message_text(
            "أرسل اسم الضربة اللي ضربت فعلياً\n"
            "(مثال: زوجين، ثلاثية، فل هاوس، أربعة أو أقوى...)\n\n"
            "أو أرسل /skip لو ما تبي تسجل"
        )
        return ASK_ACTUAL_HIT


async def handle_actual_hit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()

    if text in ["/skip", "skip", "تخطي"]:
        await update.message.reply_text("تم التخطي.")
    else:
        context.user_data["last_hand"] = text
        await update.message.reply_text(f"تم تسجيل الضربة الفعلية: {text}")

    await do_final_prediction(update, context)
    return ConversationHandler.END


async def do_final_prediction(update_or_query, context):
    last_hand = context.user_data.get("last_hand", "غير معروف")
    last_suit = context.user_data.get("last_suit", "?")
    last_rank = context.user_data.get("last_rank", "?")

    predictions = generate_name_predictions(last_hand)
    random.shuffle(predictions)
    top_preds = predictions[:4]

    lines = ["التوقعات للضربة القادمة:\n"]
    for i, pred in enumerate(top_preds, 1):
        if "crash" in pred.lower():
            lines.append(f"⚠️ {pred}")
        elif i == 1:
            lines.append(f"الأكثر احتمالاً: {pred}")
        elif i == 2:
            lines.append(f"احتمال جيد: {pred}")
        else:
            lines.append(f"احتمال متوسط: {pred}")

    lines.append(f"\nبناءً على:")
    lines.append(f"• آخر ضربة: {last_hand}")
    if last_rank != "?" and last_suit != "?":
        lines.append(f"• آخر ورقة: {last_rank} {last_suit}")

    final_text = "\n".join(lines)

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(final_text)
    else:
        await update_or_query.message.reply_text(final_text)

    context.user_data["pending_hand"] = last_hand


async def save_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip().lower()
    if not text.startswith("x"):
        return

    try:
        _ = float(text[1:])
    except ValueError:
        await update.message.reply_text("الصيغة خاطئة → مثال: x2.8")
        return

    await update.message.reply_text("تم حفظ النتيجة ✓ شكراً")


def main():
    app = Application.builder().token(TOKEN).build()

    conv_choice = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]},
        fallbacks=[],
    )

    conv_predict = ConversationHandler(
        entry_points=[CommandHandler("predict", cmd_predict)],
        states={
            PREDICT_HAND: [CallbackQueryHandler(button_handler)],
            PREDICT_SUIT: [CallbackQueryHandler(button_handler)],
            PREDICT_RANK: [CallbackQueryHandler(button_handler)],
            ASK_ACTUAL_HIT: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_actual_hit)
            ],
        },
        fallbacks=[],
    )

    app.add_handler(conv_choice)
    app.add_handler(conv_predict)
    app.add_handler(MessageHandler(filters.Regex(r'^x[\d.]+$'), save_result))
    app.add_handler(CommandHandler("activate", activate))

    app.job_queue.run_repeating(send_update, interval=600, first=30)

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
