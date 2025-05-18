
import logging
import random
import os
import json
import time
import telegram.error
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from gtts import gTTS
from dotenv import load_dotenv
from db import init_db, add_user, save_progress, get_progress

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

logging.basicConfig(level=logging.INFO)

# Локализация
LOCALES = {}
LOCALE_PATH = "locales.json"
def load_locales():
    global LOCALES
    try:
        with open(LOCALE_PATH, encoding="utf-8") as f:
            LOCALES = json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки языков: {e}")

def t(key, context, **kwargs):
    lang = context.user_data.get("lang", "en")
    text = LOCALES.get(lang, {}).get(key, key)
    return text.format(**kwargs)

load_locales()
LANGUAGE_OPTIONS = [(code, LOCALES[code].get("language_label", code)) for code in LOCALES]

# Слова по темам
WORDS_BY_TOPIC = {}
def load_word_topics(folder="word_topics"):
    for filename in os.listdir(folder):
        if filename.endswith(".json"):
            topic = filename[:-5]
            with open(os.path.join(folder, filename), encoding="utf-8") as f:
                WORDS_BY_TOPIC[topic] = json.load(f)

load_word_topics()

def cleanup_old_mp3(folder="audio", max_age_minutes=30):
    now = time.time()
    max_age = max_age_minutes * 60
    if not os.path.exists(folder):
        return
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if name.endswith(".mp3") and os.path.isfile(path):
            if now - os.path.getmtime(path) > max_age:
                os.remove(path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id, update.effective_user.username or "")
    await choose_language(update, context)

async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(label, callback_data=f"lang_{code}")] for code, label in LANGUAGE_OPTIONS]
    await update.message.reply_text("Choose your language:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_code = query.data.replace("lang_", "")
    if lang_code in LOCALES:
        context.user_data["lang"] = lang_code
        await query.message.reply_text(t("about", context), parse_mode="HTML")
        await query.message.reply_text(
            t("start", context, name=query.from_user.first_name),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(topic.capitalize(), callback_data=f"topic_{topic}")]
                for topic in WORDS_BY_TOPIC
            ])
        )
    else:
        await query.message.reply_text("❌ Unsupported language.")

async def show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        t("choose_topic", context),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(topic.capitalize(), callback_data=f"topic_{topic}")]
            for topic in WORDS_BY_TOPIC
        ])
    )

async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.replace("topic_", "")
    context.user_data["topic"] = topic
    await query.message.reply_text(t("topic_chosen", context, topic=topic.capitalize()), parse_mode="HTML")
    await handle_word(update, context)
    await query.message.reply_text(
        t("test_prompt", context),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("test_button", context), callback_data="new_test")]])
    )

async def handle_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = context.user_data.get("topic")
    words = WORDS_BY_TOPIC.get(topic, [])
    word = random.choice(words)
    lang = context.user_data.get("lang", "en")
    translation = word.get(lang, word["en"])
    text = f"<b>{word['nl']}</b> — {translation}\n<i>{word['example']}</i>"
    os.makedirs("audio", exist_ok=True)
    cleanup_old_mp3()
    filename = f"audio/{word['nl'].replace(' ', '_')}.mp3"
    try:
        gTTS(word['nl'], lang='nl').save(filename)
        with open(filename, "rb") as audio:
            await query.message.reply_audio(audio=audio, caption=text, parse_mode="HTML")
    except Exception:
        await query.message.reply_text(text)

    await query.message.reply_text(
        t("want_more", context),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("new_word_button", context), callback_data="new_word")]])
    )

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    send = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    topic = context.user_data.get("topic")
    word = random.choice(WORDS_BY_TOPIC.get(topic, []))
    correct = word.get("en")
    wrong = [w.get("en") for t in WORDS_BY_TOPIC.values() for w in t if w.get("en") != correct]
    options = random.sample(wrong, 2) + [correct]
    random.shuffle(options)
    context.user_data["test_word"] = word
    buttons = [[InlineKeyboardButton(opt, callback_data=f"answer_{opt}")] for opt in options]
    await send.reply_text(
        f"{t('test_question', context, word=word['nl'])}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected = query.data.replace("answer_", "")
    word = context.user_data.get("test_word")
    correct = word["en"]
    if selected == correct:
        msg = t("test_correct", context, word=word["nl"], answer=correct)
    else:
        msg = t("test_wrong", context, word=word["nl"], correct=correct, answer=selected)
    await query.message.reply_text(msg)
    await query.message.reply_text(
        t("test_next", context),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪", callback_data="new_test")]])
    )

async def new_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await start_test(update, context)

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide your feedback after the command. Example: /feedback I love it!")
        return
    user = update.effective_user
    feedback_text = " ".join(context.args)

    await update.message.reply_text("✅ Thanks for your feedback!")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    from db import get_user_count
    count = get_user_count()
    await update.message.reply_text(f"👥 Total users: {count}")

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("language", "Change interface language"),
        BotCommand("topic", "Choose a topic"),
        BotCommand("feedback", "Send feedback to the admin")
    ])

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", choose_language))
    app.add_handler(CommandHandler("topic", show_topics))
    app.add_handler(CommandHandler("test", start_test))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: None))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(choose_topic, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(handle_word, pattern="^new_word$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    app.add_handler(CallbackQueryHandler(new_test_question, pattern="^new_test$"))

    print("✅ Бот запущен...")
    print("📡 Starting polling mode...")

    try:
        app.run_polling()
    except telegram.error.Conflict:
        print("❌ Another polling instance is already running. Exiting.")

if __name__ == "__main__":
    main()
