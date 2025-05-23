import asyncio
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
from db import (
    init_db, add_user, get_current_users_count,
    get_new_users_by_day, get_new_users_by_week,
    get_left_users_count, get_country_statistics
)

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


async def notify_users_after_restart(app):
    from db import get_all_users
    for user_id in get_all_users():
        try:
            await app.bot.send_message(
                chat_id=user_id,
                text="🛠️ The bot was updated and is now ready to use again. Thanks for your patience!"
            )
        except Exception as e:
            logging.warning(f"Could not notify user {user_id}: {e}")


# --- Command handler: /users ---
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access denied.")
        return

    total = get_current_users_count()
    new_by_day = get_new_users_by_day()
    new_by_week = get_new_users_by_week()
    left = get_left_users_count()
    countries = get_country_statistics()

    message = f"📊 <b>Bot Statistics</b>\n"
    message += f"👥 Current users: <b>{total}</b>\n"
    message += f"➕ New today: <b>{new_by_day}</b>\n"
    message += f"📈 New this week: <b>{new_by_week}</b>\n"
    message += f"➖ Users left: <b>{left}</b>\n\n"

    if countries:
        message += "🌍 Users by country:\n"
        for country, count in countries.items():
            message += f"  {country}: {count}\n"

    await update.message.reply_text(message, parse_mode="HTML")






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
        keyboard.append([InlineKeyboardButton("📘 Grammar", callback_data="grammar_menu")])

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
    keyboard.append([InlineKeyboardButton("📘 Grammar", callback_data="grammar_menu")])

    await update.message.reply_text(
        t("start", context),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
            await query.message.reply_voice(voice=audio, caption=text, parse_mode="HTML")
        os.remove(filename)
    except Exception:
        await query.message.reply_text(text)
    await query.message.reply_text(
        "📘", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("new_word_button", context), callback_data="new_word")]]))





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
    
    await query.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("test_next", context), callback_data="new_test")]])
    )








async def new_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await start_test(update, context)





async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide your feedback after the command. Example: /feedback I love it!")
        return
    await update.message.reply_text("✅ Thanks for your feedback!")








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






async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    if not context.args:
        await update.message.reply_text("❗ Please provide a message. Example: /message Hello everyone!")
        return

    from db import get_all_users
    text = " ".join(context.args)
    count = 0
    for user_id in get_all_users():
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            count += 1
        except Exception as e:
            logging.warning(f"Failed to send message to {user_id}: {e}")
    await update.message.reply_text(f"✅ Sent to {count} users.")

# РАЗДЕЛ ГРАММАТИКИ
# Функция загрузки грамматических тем

GRAMMAR_TOPICS = {}

def load_grammar_topics(path="grammar.json"):
    global GRAMMAR_TOPICS
    try:
        with open(path, encoding="utf-8") as f:
            GRAMMAR_TOPICS = json.load(f)
    except Exception as e:
        logging.warning(f"Could not load grammar topics: {e}")

load_grammar_topics()

# Добавляет кнопку Грамматика:
async def show_grammar_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topics = list(WORDS_BY_TOPIC)
    keyboard = [
        [InlineKeyboardButton(topics[i].capitalize(), callback_data=f"topic_{topics[i]}")]
        + ([InlineKeyboardButton(topics[i+1].capitalize(), callback_data=f"topic_{topics[i+1]}")] if i + 1 < len(topics) else [])
        for i in range(0, len(topics), 2)
    ]
    keyboard.append([InlineKeyboardButton("📘 Grammar", callback_data="grammar_menu")])
    await update.message.reply_text(t("start", context), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))



# Хендлер для выбора грамматической темы
async def show_grammar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "en")

    buttons = []
    items = list(GRAMMAR_TOPICS.items())
    for i in range(0, len(items), 4):
        row = []
        for key, data in items[i:i+4]:
            label = data["title"].get(lang, key)
            row.append(InlineKeyboardButton(label, callback_data=f"grammar_{key}"))
        buttons.append(row)

    await query.message.reply_text("📘 Choose a grammar topic:", reply_markup=InlineKeyboardMarkup(buttons))


# Хендлер показа содержимого грамматической темы
async def show_grammar_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("grammar_", "")
    lang = context.user_data.get("lang", "en")
    content = GRAMMAR_TOPICS.get(key, {}).get("content", {}).get(lang)

    if content:
        await query.message.reply_text(content, parse_mode="HTML")
    else:
        await query.message.reply_text("❌ Content not found.")







def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()
    app.post_init(lambda app: asyncio.create_task(notify_users_after_restart(app)))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", choose_language))
    app.add_handler(CommandHandler("topic", show_topics))
    app.add_handler(CommandHandler("test", start_test))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("donate", donate))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("message", broadcast_message))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, define_word))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^lang_"))
    app.add_handler(CallbackQueryHandler(choose_topic, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(handle_word, pattern="^new_word$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    app.add_handler(CallbackQueryHandler(new_test_question, pattern="^new_test$"))

    app.add_handler(CallbackQueryHandler(show_grammar_menu, pattern="^grammar_menu$"))
    app.add_handler(CallbackQueryHandler(show_grammar_content, pattern="^grammar_"))
    

    print("✅ Bot is running...")
    print("📡 Polling mode started.")

    try:
        app.run_polling()
    except telegram.error.Conflict:
        print("❌ Another polling instance is already running. Exiting.")

if __name__ == "__main__":
    main()





