import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
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
    raise ValueError("TOKEN غير موجود في الـ Environment Variables")

ACTIVATION_CODE = "SECRET123"           # غيّره لشي أقوى أو اجعله عشوائي لاحقاً

SA_TIMEZONE = ZoneInfo("Asia/Riyadh")

# نصوص
WELCOME_MSG = (
    "مرحبا! 🚀\n"
    "راح أسألك سؤال واحد علمود أعطيك الضربة المناسبة.\n"
    "اضغط على الخيار اللي تريده ↓"
)

QUESTION = "شنو نوع الضربة اللي تريده؟"

OPTIONS = [
    ["ربح متزايد"],
    ["بس أربعة"],
    ["بس دبل AA"],
    ["دبل AA وأربعة"],
]

RESPONSES = {
    "ربح متزايد": (
        "اختيارك: **ربح متزايد**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: أسبوع واحد\n\n"
        "→ للتفعيل أرسل:\n"
        f"`/activate {ACTIVATION_CODE}`\n\n"
        "بعد التفعيل راح تبدأ تتلقى الأوقات كل 10 دقايق."
    ),
    "بس أربعة": "اختيارك: **بس أربعة** – السعر 10,000 – مدة يوم\nتواصل وياي: t.me/اسمك",
    "بس دبل AA": "اختيارك: **بس دبل AA** – السعر 10,000 – مدة يومين\nتواصل وياي: t.me/اسمك",
    "دبل AA وأربعة": "اختيارك: **دبل AA وأربعة** – السعر 20,000 – مدة 3 أيام\nتواصل وياي: t.me/اسمك",
}

# ────────────────────────────────────────────────
# حفظ الاختيارات والتفعيلات (في الذاكرة – يتمسح عند إعادة التشغيل)
# ────────────────────────────────────────────────

def get_user_choice(context, user_id):
    return context.application.bot_data.get("user_choices", {}).get(user_id)

def save_user_choice(context, user_id, choice):
    choices = context.application.bot_data.setdefault("user_choices", {})
    choices[user_id] = choice

def is_activated(context, user_id):
    return user_id in context.application.bot_data.get("activated_users", {})

def activate_user(context, user_id, choice):
    activated = context.application.bot_data.setdefault("activated_users", {})
    activated[user_id] = choice

# ────────────────────────────────────────────────
# إرسال الأوقات (كل 10 دقايق)
# ────────────────────────────────────────────────

async def send_times(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(SA_TIMEZONE)
    current_str = now.strftime("%H:%M")

    times = []
    base = now.replace(second=0, microsecond=0)
    for i in range(1, 11):
        delta_min = i * 2 + 1          # 3,5,7,9,11,... أو غيّر النمط اللي تبيه
        t = base + timedelta(minutes=delta_min)
        times.append(t.strftime("%H:%M"))

    msg = (
        f"تحديث جديد – الساعة {current_str} (شغال ✓)\n"
        "أوقات مقترحة (ربح متزايد):\n" +
        " • " + "\n • ".join(times) + "\n\n"
        "التحديث التالي بعد ~10 دقايق"
    )

    activated = context.application.bot_data.get("activated_users", {})
    for uid, ch in activated.items():
        if ch == "ربح متزايد":
            try:
                await context.bot.send_message(uid, msg)
            except Exception as e:
                logger.warning(f"فشل إرسال لـ {uid}: {e}")

# ────────────────────────────────────────────────
# Handlers
# ────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = ReplyKeyboardMarkup(OPTIONS, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(WELCOME_MSG, reply_markup=kb)
    await update.message.reply_text(QUESTION)
    return 0  # CHOICE state


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text not in RESPONSES:
        await update.message.reply_text("اختار من الأزرار أعلاه لو سمحت")
        return 0

    user_id = update.effective_user.id
    save_user_choice(context, user_id, text)

    await update.message.reply_text(
        RESPONSES[text],
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return -1  # END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].strip() != ACTIVATION_CODE:
        await update.message.reply_text(f"الكود غلط\nاستخدم: /activate {ACTIVATION_CODE}")
        return

    user_id = update.effective_user.id
    choice = get_user_choice(context, user_id)

    if not choice:
        await update.message.reply_text("أول شي اختار نوع الضربة من /start")
        return

    if is_activated(context, user_id):
        await update.message.reply_text("حسابك مفعّل مسبقاً")
        return

    activate_user(context, user_id, choice)

    now_str = datetime.now(SA_TIMEZONE).strftime("%H:%M")
    await update.message.reply_text(
        f"تم التفعيل بنجاح! ✅\n"
        f"نوع الضربة: {choice}\n"
        f"الساعة الحالية: {now_str}\n"
        "راح تبدأ تتلقى التحديثات كل 10 دقايق (أول واحد خلال دقايق)"
    )


def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]},
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("activate", activate))

    # جدولة كل 600 ثانية (10 دقايق)
    app.job_queue.run_repeating(send_times, interval=600, first=30)

    logger.info("البوت بدأ التشغيل")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
