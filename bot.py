# bot.py
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# ------------------ إعداد اللوغ ------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالات المحادثة
CHOICE = 0

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN is not set in environment variables!")

# رمز التفعيل (غيّره لشي أقوى أو اجعله عشوائي لكل مستخدم)
ACTIVATION_CODE = "SECRET123"   # مثال: /activate SECRET123

# نصوص
WELCOME = (
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
        "→ للتفعيل أرسل الكوماند التالي:\n"
        f"`/activate {ACTIVATION_CODE}`\n\n"
        "بعد التفعيل راح يبدأ إرسال الأوقات كل 10 دقايق."
    ),
    "بس أربعة": (
        "اختيارك: **بس أربعة**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: يوم واحد\n\n"
        "→ تواصل وياي للدفع والتشغيل: t.me/YourUsername"
    ),
    # ... باقي الخيارات نفسها بدون تفعيل أوتوماتيكي
    "بس دبل AA": (
        "اختيارك: **بس دبل AA**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: يومين\n\n"
        "→ تواصل وياي: t.me/YourUsername"
    ),
    "دبل AA وأربعة": (
        "اختيارك: **دبل AA وأربعة**\n"
        "السعر: 20,000 مغلف\n"
        "المدة: 3 أيام\n\n"
        "→ تواصل وياي: t.me/YourUsername"
    ),
}

# ------------------ دالة إرسال الأوقات كل 10 دقايق ------------------
async def send_times(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(ZoneInfo("Asia/Riyadh"))
    current_time_str = now.strftime("%H:%M")

    base_time = now.replace(second=0, microsecond=0)
    times = []
    for i in range(1, 11):  # مثال: 10 أوقات قادمة
        next_time = base_time + timedelta(minutes=i * 2 + 1)  # 1,3,5,7,... دقايق
        times.append(next_time.strftime("%H:%M"))

    message = (
        f"الساعة الحالية: {current_time_str} بتوقيت السعودية\n"
        "أوقات الضربات القادمة (ربح متزايد):\n"
        " • " + "\n • ".join(times) + "\n\n"
        "تابع التحديث كل 10 دقايق."
    )

    # أرسل لكل مستخدم مفعّل وخياره "ربح متزايد"
    activated_users = context.application.bot_data.get("activated_users", {})
    for user_id, choice in activated_users.items():
        if choice == "ربح متزايد":
            try:
                await context.bot.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.warning(f"فشل إرسال لـ {user_id}: {e}")


# ------------------ handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(
        OPTIONS, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(WELCOME, reply_markup=reply_markup)
    await update.message.reply_text(QUESTION)
    return CHOICE


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    if text in RESPONSES:
        await update.message.reply_text(
            RESPONSES[text],
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "اختيار غير صحيح، جرب من الأزرار.",
            reply_markup=ReplyKeyboardMarkup(OPTIONS, resize_keyboard=True, one_time_keyboard=True)
        )
        return CHOICE

    return ConversationHandler.END


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(f"استخدم: /activate {ACTIVATION_CODE}")
        return

    code = context.args[0].strip()
    if code != ACTIVATION_CODE:
        await update.message.reply_text("الرمز غلط! جرب مرة ثانية.")
        return

    user_id = update.effective_user.id

    # نفترض إن الخيار محفوظ سابقاً (من خلال الاختيار)
    # لو ما اختار قبل → نقول له يختار أول
    choice = context.application.bot_data.get("user_choices", {}).get(user_id)
    if not choice:
        await update.message.reply_text("أول شي اختار نوع الضربة من /start")
        return

    # حفظ التفعيل
    activated = context.application.bot_data.setdefault("activated_users", {})
    activated[user_id] = choice

    await update.message.reply_text(
        "تم التفعيل بنجاح! ✅\n"
        "راح تبدأ تتلقى الأوقات كل 10 دقايق (لخيارك: " + choice + ")"
    )


def main():
    application = Application.builder().token(TOKEN).build()

    # Conversation للاختيار
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)]},
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)

    # كوماند التفعيل
    application.add_handler(CommandHandler("activate", activate))

    # جدولة كل 10 دقايق (600 ثانية)
    application.job_queue.run_repeating(
        send_times,
        interval=600,          # 10 دقايق
        first=30,              # يبدأ بعد 30 ثانية من التشغيل
    )

    logger.info("البوت شغال...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
