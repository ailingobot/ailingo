import logging
import random
import os
import json
import time
import telegram.error
import httpx
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from gtts import gTTS
from dotenv import load_dotenv
from db import init_db, add_user, get_user_count

# --- Config ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

logging.basicConfig(level=logging.INFO)

# --- Localization ---
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

# --- Word Topics ---
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

# --- Handlers ---
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
        topics = list(WORDS_BY_TOPIC)
        keyboard = [
            [InlineKeyboardButton(topics[i].capitalize(), callback_data=f"topic_{topics[i]}")]
            + ([InlineKeyboardButton(topics[i+1].capitalize(), callback_data=f"topic_{topics[i+1]}")] if i + 1 < len(topics) else [])
            for i in range(0, len(topics), 2)
        ]
        await query.message.reply_text(
            t("start", context, name=query.from_user.first_name),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.message.reply_text("❌ Unsupported language.")

async def show_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = list(WORDS_BY_TOPIC)
    keyboard = [
        [InlineKeyboardButton(topics[i].capitalize(), callback_data=f"topic_{topics[i]}")]
        + ([InlineKeyboardButton(topics[i+1].capitalize(), callback_data=f"topic_{topics[i+1]}")] if i + 1 < len(topics) else [])
        for i in range(0, len(topics), 2)
    ]
    await update.message.reply_text(t("choose_topic", context), reply_markup=InlineKeyboardMarkup(keyboard))

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
            await query.message.reply_voice(voice=audio, caption=text, parse_mode="HTML")
        os.remove(filename)
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
    await update.message.reply_text("✅ Thanks for your feedback!")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    count = get_user_count()
    await update.message.reply_text(f"👥 Total users: {count}")

async def donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Support this project on Buy Me a Coffee!"
    button = InlineKeyboardMarkup([[InlineKeyboardButton("☕ Buy me a coffee", url="https://buymeacoffee.com/ailingo")]])
    await update.message.reply_text(text, reply_markup=button, parse_mode="HTML")

async def define_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = update.message.text.strip().lower()
    if not word.isalpha():
        return
    await update.message.chat.send_action("typing")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
            if response.status_code != 200:
                await update.message.reply_text(f"❌ No definition found for “{word}”.")
                return
            data = response.json()
            definition = data[0]["meanings"][0]["definitions"][0]["definition"]
            example = data[0]["meanings"][0]["definitions"][0].get("example", "")
            msg = f"📘 <b>{word}</b>\n— {definition}"
            if example:
                msg += f"\n\n<i>Example:</i> {example}"
            await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        logging.exception("Error fetching definition")
        await update.message.reply_text("⚠️ Something went wrong while fetching the definition.")

async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("language", "Change interface language"),
        BotCommand("topic", "Choose a topic"),
        BotCommand("feedback", "Send feedback to the admin"),
        BotCommand("donate", "Support the project")
    ])

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", choose_language))
    app.add_handler(CommandHandler("topic", show_topics))
    app.add_handler(CommandHandler("test", start_test))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("donate", donate))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, define_word))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(choose_topic, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(handle_word, pattern="^new_word$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    app.add_handler(CallbackQueryHandler(new_test_question, pattern="^new_test$"))

    print("✅ Bot is running...")
    print("📡 Polling mode started.")

    try:
        app.run_polling()
    except telegram.error.Conflict:
        print("❌ Another polling instance is already running. Exiting.")

if __name__ == "__main__":
    main()
