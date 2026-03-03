import os
import logging
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# Logging
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
    raise ValueError("التوكن غير موجود! ضعه في Environment Variables → TOKEN")

ACTIVATION_CODE = "SECRET123"  # غيّره لاحقاً

SA_TZ = ZoneInfo("Asia/Riyadh")

# حالات المحادثة (نستخدم أرقام مباشرة لتجنب الأخطاء)
CHOOSING = 0
PREDICT = 1

# تخزين بيانات بسيط
def is_activated(context, user_id: int) -> bool:
    return user_id in context.application.bot_data.get("activated", {})

def activate_user(context, user_id: int, choice: str):
    activated = context.application.bot_data.setdefault("activated", {})
    activated[user_id] = choice

# تنبؤ بسيط جداً
def get_prediction(last_type: str, history: list) -> float:
    if not history:
        return round(random.uniform(1.7, 4.0), 2)
    avg = sum(history) / len(history)
    if "أربع" in last_type or "فل" in last_type:
        return round(random.uniform(1.3, 2.3), 2)
    if len(history) >= 3 and all(x >= 3 for x in history[-3:]):
        return round(random.uniform(1.4, 2.2), 2)
    return round(random.uniform(avg * 0.85, avg * 1.35), 2)

# ────────────────────────────────────────────────
# أوامر ومعالجات
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
    valid = ["ربح متزايد", "بس أربعة", "بس دبل AA", "دبل AA وأربعة"]
    
    if text not in valid:
        await update.message.reply_text("اختيار غير صحيح، جرب من الأزرار.")
        return CHOOSING
    
    user_id = update.effective_user.id
    context.user_data["choice"] = text
    
    msg = f"اختيارك: *{text}*\n\n"
    if text == "ربح متزايد":
        msg += f"للتفعيل أرسل:\n`/activate {ACTIVATION_CODE}`"
    else:
        msg += "تواصل معي للدفع: @اسمك"
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] != ACTIVATION_CODE:
        await update.message.reply_text(f"كود خاطئ!\nاستخدم: /activate {ACTIVATION_CODE}")
        return
    
    user_id = update.effective_user.id
    choice = context.user_data.get("choice")
    
    if not choice:
        await update.message.reply_text("اختار نوع الخدمة أولاً من /start")
        return
    
    if is_activated(context, user_id):
        await update.message.reply_text("حسابك مفعّل مسبقاً.")
        return
    
    activate_user(context, user_id, choice)
    
    await update.message.reply_text(
        f"تم التفعيل بنجاح ✅\n"
        f"النوع: {choice}\n\n"
        "الآن متاح لك:\n"
        "• /predict    ← خمن الضربة\n"
        "• أرسل x2.5   ← سجّل النتيجة الفعلية"
    )


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    if not is_activated(context, user_id):
        await update.message.reply_text(
            "ميزة التنبؤ للمشتركين المفعّلين فقط.\n"
            "أرسل /start ثم /activate"
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "أرسل ثلاثة أسطر:\n"
        "1. نوع الورقة (قلب/جو/رتل/بستوني)\n"
        "2. الكروت المكشوفة\n"
        "3. آخر ضربة (زوج، ثلاثة، أربعة، فل هاوس...)"
    )
    return PREDICT


async def handle_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lines = [line.strip() for line in update.message.text.splitlines() if line.strip()]
    if len(lines) < 3:
        await update.message.reply_text("أرسل ثلاثة أسطر منفصلة.")
        return PREDICT
    
    suit, cards, last_hit = lines[:3]
    last_hit = last_hit.lower()
    
    hist_dict = context.application.bot_data.setdefault("history", {})
    user_hist = hist_dict.setdefault(update.effective_user.id, deque(maxlen=10))
    recent_mults = [m for _, m in user_hist]
    
    pred = get_prediction(last_hit, recent_mults)
    
    await update.message.reply_text(
        f"التنبؤ: **x{pred:.2f}**\n\n"
        f"نوع: {suit}\n"
        f"كروت: {cards}\n"
        f"آخر ضربة: {last_hit}\n\n"
        "بعد النتيجة أرسل مثل: x3.1"
    )
    
    context.user_data["last_pred"] = pred
    context.user_data["last_hit"] = last_hit
    return ConversationHandler.END


async def save_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip().lower()
    if not text.startswith("x") or len(text) < 2:
        return
    
    try:
        val = float(text[1:])
    except ValueError:
        await update.message.reply_text("صيغة خاطئة، مثال: x2.8")
        return
    
    if "last_pred" not in context.user_data:
        return
    
    user_id = update.effective_user.id
    pred = context.user_data.pop("last_pred", None)
    hit = context.user_data.pop("last_hit", "غير معروف")
    
    hist_dict = context.application.bot_data.setdefault("history", {})
    user_hist = hist_dict.setdefault(user_id, deque(maxlen=10))
    user_hist.append((hit, val))
    
    diff = abs(pred - val) if pred else 0
    await update.message.reply_text(
        f"تم التسجيل: {text}\n"
        f"التنبؤ السابق: x{pred:.2f}\n"
        f"الفرق: ±{diff:.2f}"
    )


# ────────────────────────────────────────────────
# الجدولة (كل 10 دقائق)
# ────────────────────────────────────────────────

async def send_update(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(SA_TZ).strftime("%H:%M")
    msg = f"تحديث {now} – أوقات مقترحة:\n" + "\n".join([f"• {t}" for t in ["15:18", "15:22", "15:26"]])  # مثال
    
    activated = context.application.bot_data.get("activated", {})
    for uid, ch in activated.items():
        if ch == "ربح متزايد":
            try:
                await context.bot.send_message(uid, msg)
            except:
                pass


def main():
    print("جاري تشغيل البوت...")
    
    app = Application.builder().token(TOKEN).build()
    print("Application تم إنشاؤها")
    
    # محادثة الاختيار
    conv_choice = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]
        },
        fallbacks=[],
    )
    
    # محادثة التنبؤ
    conv_predict = ConversationHandler(
        entry_points=[CommandHandler("predict", cmd_predict)],
        states={
            PREDICT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_predict)]
        },
        fallbacks=[],
    )
    
    app.add_handler(conv_choice)
    app.add_handler(conv_predict)
    app.add_handler(MessageHandler(filters.Regex(r'^x[\d.]+$'), save_result))
    app.add_handler(CommandHandler("activate", activate))
    
    app.job_queue.run_repeating(send_update, interval=600, first=10)
    
    print("كل الهاندلرز تم إضافتها – بدء polling")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
