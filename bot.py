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

ACTIVATION_CODE = "SECRET123"  # غيّره إلى كود قوي

SA_TZ = ZoneInfo("Asia/Riyadh")

# حالات المحادثة
ASK_RANK, ASK_SUIT, ASK_LAST_HIT, ASK_ACTUAL_HIT = range(4)

# خيارات الأرقام
RANK_OPTIONS = [
    ["2", "3", "4", "5"],
    ["6", "7", "8", "9"],
    ["10", "J", "Q", "K", "A"],
    ["↩️ إلغاء"]
]

SUIT_EMOJIS = ["♥️", "♦️", "♣️", "♠️", "↩️ رجوع"]

# الضربات المحدودة فقط (اللي طلبتها)
HIT_OPTIONS = [
    ["أربعة من نوع واحد", "زوجين"],
    ["فل هاوس", "متتالية"],
    ["ثلاثة"],
    ["↩️ إلغاء"]
]

# ────────────────────────────────────────────────
# دوال مساعدة
# ────────────────────────────────────────────────

def is_activated(context, user_id: int) -> bool:
    return user_id in context.application.bot_data.get("activated", {})

def activate_user(context, user_id: int, choice: str):
    activated = context.application.bot_data.setdefault("activated", {})
    activated[user_id] = choice

def get_smart_prediction(last_hit: str, history: deque) -> list:
    """
    توقع ذكي يعتمد على التاريخ المحفوظ
    """
    if not history:
        return ["زوجين", "ثلاثة", "فل هاوس", "أربعة من نوع واحد"]

    recent_hits = [h for h, _ in list(history)[-6:]]  # آخر 6 جولات

    count = {}
    for h in recent_hits:
        count[h] = count.get(h, 0) + 1

    most_common = max(count, key=count.get) if count else "زوجين"

    if "أربعة" in last_hit or "فل هاوس" in last_hit:
        return ["زوج", "زوجين", "ثلاثة", "احتمال crash عالي"]

    if most_common == "ثلاثة":
        return ["زوجين", "فل هاوس", "أربعة من نوع واحد", "متتالية"]
    if most_common == "زوجين":
        return ["ثلاثة", "فل هاوس", "أربعة من نوع واحد", "متتالية"]
    if most_common == "فل هاوس":
        return ["أربعة من نوع واحد", "ثلاثة", "زوجين", "احتمال crash"]

    return ["زوجين", "ثلاثة", "فل هاوس", "أربعة من نوع واحد"]

async def start_new_round(update_or_query, context, edit=True):
    """يبدأ جولة جديدة تلقائياً"""
    keyboard = []
    for row in RANK_OPTIONS:
        keyboard.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in row])

    text = "جولة جديدة بدأت!\nأولاً: اختر رقم آخر ورقة مكشوفة"

    if edit and hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        if hasattr(update_or_query, "message"):
            await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update_or_query.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    return ASK_RANK

# ────────────────────────────────────────────────
# Handlers
# ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [["ربح متزايد"], ["بس أربعة"], ["بس دبل AA"], ["دبل AA وأربعة"]]
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
        "اضغط /predict لبدء التخمين"
    )


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_activated(context, update.effective_user.id):
        await update.message.reply_text("يجب التفعيل أولاً → /start ثم /activate")
        return ConversationHandler.END

    keyboard = []
    for row in RANK_OPTIONS:
        keyboard.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in row])

    await update.message.reply_text("جولة جديدة\nأولاً: اختر رقم آخر ورقة مكشوفة", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_RANK


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("rank_"):
        rank = data[5:]
        if rank == "↩️ إلغاء":
            await query.edit_message_text("تم الإلغاء.")
            return ConversationHandler.END

        context.user_data["last_rank"] = rank

        keyboard = [[InlineKeyboardButton(e, callback_data=f"suit_{e}")] for e in SUIT_EMOJIS]
        await query.edit_message_text(
            f"رقم الورقة: {rank}\n\nثانياً: اختر نوع الورقة",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_SUIT

    elif data.startswith("suit_"):
        suit = data[5:]
        if suit == "↩️ رجوع":
            keyboard = []
            for row in RANK_OPTIONS:
                keyboard.append([InlineKeyboardButton(r, callback_data=f"rank_{r}") for r in row])
            await query.edit_message_text("اختر رقم الورقة:", reply_markup=InlineKeyboardMarkup(keyboard))
            return ASK_RANK

        context.user_data["last_suit"] = suit

        keyboard = []
        for row in HIT_OPTIONS:
            keyboard.append([InlineKeyboardButton(txt, callback_data=f"hit_{txt}") for txt in row])

        await query.edit_message_text(
            f"رقم: {context.user_data['last_rank']}\n"
            f"نوع: {suit}\n\n"
            "ثالثاً: اختر آخر ضربة حصلت",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_LAST_HIT

    elif data.startswith("hit_"):
        hit = data[4:]
        if hit == "↩️ إلغاء":
            await query.edit_message_text("تم الإلغاء.")
            return ConversationHandler.END

        context.user_data["last_hit"] = hit

        # التخمين المباشر
        await do_smart_prediction(query, context)

        # سؤال الضربة الفعلية أوتوماتيكياً
        keyboard = []
        for row in HIT_OPTIONS:
            keyboard.append([InlineKeyboardButton(txt, callback_data=f"actual_{txt}") for txt in row])

        await query.message.reply_text(
            "التخمين تم!\n\nالآن: شنو الضربة اللي ضربت فعلياً؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_ACTUAL_HIT

    elif data.startswith("actual_"):
        actual = data[7:]
        uid = query.from_user.id
        history = context.application.bot_data.setdefault("smart_history", {}).setdefault(uid, deque(maxlen=20))

        if actual != "↩️ إلغاء":
            history.append((
                context.user_data.get("last_hit", "غير معروف"),
                context.user_data.get("last_rank", "?"),
                context.user_data.get("last_suit", "?"),
                actual
            ))
            await query.message.reply_text(f"تم حفظ: الضربة الفعلية = {actual}")
        else:
            await query.message.reply_text("تم التخطي بدون حفظ")

        # بدء جولة جديدة تلقائياً
        await start_new_round(query, context, edit=False)
        return ASK_RANK

    return ConversationHandler.END


async def do_smart_prediction(query, context):
    last_hit = context.user_data.get("last_hit", "غير معروف")
    last_suit = context.user_data.get("last_suit", "?")
    last_rank = context.user_data.get("last_rank", "?")

    uid = query.from_user.id
    history = context.application.bot_data.setdefault("smart_history", {}).get(uid, deque())

    predictions = get_smart_prediction(last_hit, history)
    random.shuffle(predictions)
    top_preds = predictions[:4]

    lines = ["التخمين للضربة الجاية:\n"]
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
    lines.append(f"• رقم الورقة: {last_rank}")
    lines.append(f"• نوع الورقة: {last_suit}")
    lines.append(f"• آخر ضربة: {last_hit}")

    await query.edit_message_text("\n".join(lines))


def main():
    app = Application.builder().token(TOKEN).build()

    conv_choice = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]
        },
        fallbacks=[],
    )

    conv_predict = ConversationHandler(
        entry_points=[CommandHandler("predict", cmd_predict)],
        states={
            ASK_RANK: [CallbackQueryHandler(button_handler)],
            ASK_SUIT: [CallbackQueryHandler(button_handler)],
            ASK_LAST_HIT: [CallbackQueryHandler(button_handler)],
            ASK_ACTUAL_HIT: [CallbackQueryHandler(button_handler)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_choice)
    app.add_handler(conv_predict)
    app.add_handler(CommandHandler("activate", activate))

    app.job_queue.run_repeating(send_update, interval=600, first=30)

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
