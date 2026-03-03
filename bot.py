# bot.py
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# ------------------ إعداد اللوغ (مهم للـ debugging على Railway) ------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالات المحادثة
CHOICE = 0

# التوكن من Environment Variables (Railway)
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    logger.error("TOKEN مو موجود في Environment Variables!")
    raise ValueError("TOKEN is not set in environment variables!")

# نصوص الترحيب والأسئلة
WELCOME = (
    "مرحبا! 🚀\n"
    "راح أسألك كم سؤال علمود أعطيك الضربة المناسبة.\n"
    "اضغط على الخيار اللي تريده ↓"
)

QUESTION = "شنو نوع الضربة اللي تريده؟"

# الخيارات (كل سطر صف في الكيبورد)
OPTIONS = [
    ["ربح متزايد"],
    ["بس أربعة"],
    ["بس دبل AA"],
    ["دبل AA وأربعة"],
]

# الردود حسب الاختيار
RESPONSES = {
    "ربح متزايد": (
        "اختيارك: **ربح متزايد**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: أسبوع واحد\n\n"
        "→ لازم تتواصل وياي الحين علمود طريقة الدفع وتشغيل البوت.\n"
        "اكتبلي @اسمك_هنا أو اضغط هنا: t.me/اسمك_هنا"
    ),
    "بس أربعة": (
        "اختيارك: **بس أربعة**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: يوم واحد\n\n"
        "→ تواصل وياي للدفع والتشغيل: t.me/اسمك_هنا"
    ),
    "بس دبل AA": (
        "اختيارك: **بس دبل AA**\n"
        "السعر: 10,000 مغلف\n"
        "المدة: يومين\n\n"
        "→ تواصل وياي: t.me/اسمك_هنا"
    ),
    "دبل AA وأربعة": (
        "اختيارك: **دبل AA وأربعة**\n"
        "السعر: 20,000 مغلف\n"
        "المدة: 3 أيام\n\n"
        "→ ضروري تكلمني الحين للدفع: t.me/اسمك_هنا"
    ),
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup(
        OPTIONS,
        resize_keyboard=True,
        one_time_keyboard=True,   # يختفي بعد الضغط
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
            reply_markup=ReplyKeyboardRemove()  # يزيل الكيبورد بعد الإجابة
        )
    else:
        await update.message.reply_text(
            "اختيار غير صحيح، جرب من الأزرار أعلاه ↓",
            reply_markup=ReplyKeyboardMarkup(OPTIONS, resize_keyboard=True, one_time_keyboard=True)
        )
        return CHOICE  # يرجع لنفس السؤال

    # نهاية المحادثة
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "تم إلغاء العملية.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)

    logger.info("البوت بدأ يشتغل...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
