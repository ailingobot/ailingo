import logging
import random
import os
import json
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from gtts import gTTS
from db import init_db, add_user, save_progress, get_progress
from dotenv import load_dotenv

# --- Загрузка переменных окружения ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Логгирование ---
logging.basicConfig(level=logging.INFO)

# --- Словарь тем и слов ---
WORDS_BY_TOPIC = {}

def load_word_topics(folder_path="word_topics"):
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            topic_name = filename[:-5]
            path = os.path.join(folder_path, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    words = json.load(f)
                    if isinstance(words, list) and all(isinstance(w, dict) for w in words):
                        WORDS_BY_TOPIC[topic_name] = words
                    else:
                        print(f"⚠️ Файл {filename} имеет неверный формат")
            except Exception as e:
                print(f"Ошибка загрузки {filename}: {e}")

load_word_topics()

# --- Очистка старых MP3-файлов ---
def cleanup_old_mp3(folder="audio", max_age_minutes=30):
    now = time.time()
    max_age = max_age_minutes * 60

    if not os.path.exists(folder):
        return

    for filename in os.listdir(folder):
        if filename.endswith(".mp3"):
            path = os.path.join(folder, filename)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > max_age:
                    os.remove(path)
                    logging.info(f"🗑 Удалён устаревший файл: {filename}")
            except Exception as e:
                logging.warning(f"Не удалось удалить {filename}: {e}")

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or "")
    await update.message.reply_text(
        f"👋 Привет, <b>{user.first_name}</b>! Выбери тему для изучения:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(topic.capitalize(), callback_data=f"topic_{topic}")]
            for topic in WORDS_BY_TOPIC
        ])
    )

# --- Новый перевод ---
async def handle_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    topic = context.user_data.get("topic")
    if not topic or topic not in WORDS_BY_TOPIC:
        await query.message.reply_text("⚠️ Сначала выбери тему через /start.")
        return

    words = WORDS_BY_TOPIC[topic]
    if not words:
        await query.message.reply_text("⚠️ В этой теме пока нет слов.")
        return

    word = random.choice(words)
    text = f"📌 <b>{word['nl']}</b> — {word['en']}\n📝 <i>{word['example']}</i>"


    try:
        os.makedirs("audio", exist_ok=True)
        cleanup_old_mp3("audio", max_age_minutes=30)

        filename = f"audio/{word['nl'].replace(' ', '_')}.mp3"
        tts = gTTS(word["nl"], lang="nl")
        tts.save(filename)

        save_progress(user.id, word["nl"])

        with open(filename, "rb") as audio_file:
            await query.message.reply_audio(audio=audio_file, caption=text, parse_mode="HTML")

    except Exception as e:
        logging.error(f"TTS error: {e}")
        await query.message.reply_text(f"⚠️ Ошибка озвучки: {e}")

    await query.message.reply_text("👉 Хочешь ещё?", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Новое слово", callback_data="new_word")]
    ]))

# --- /progress ---
async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    count = get_progress(user.id)
    await update.message.reply_text(f"📊 Ты уже выучил {count} слов! 💪")

# --- Выбор темы ---
async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.replace("topic_", "")
    if topic not in WORDS_BY_TOPIC:
        await query.message.reply_text("❌ Тема не найдена")
        return
    context.user_data["topic"] = topic
    await query.message.reply_text(f"Вы выбрали тему: <b>{topic.capitalize()}</b>. Вот первое слово:", parse_mode="HTML")
    await handle_word(update, context)

# --- /test ---
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    send_target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()

    topic = context.user_data.get("topic")
    if not topic:
        await send_target.reply_text("⚠️ Сначала выбери тему через /start.")
        return

    word = random.choice(WORDS_BY_TOPIC[topic])
    correct = word["en"]

    all_words = [w["en"] for t in WORDS_BY_TOPIC.values() for w in t if w["en"] != correct]
    wrong_answers = random.sample(all_words, 2)
    options = wrong_answers + [correct]
    random.shuffle(options)

    context.user_data["test_word"] = word

    buttons = [[InlineKeyboardButton(opt, callback_data=f"answer_{opt}")] for opt in options]
    await send_target.reply_text(
        f"❓ Как переводится слово: <b>{word['nl']}</b>?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# --- Ответ на тест ---
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = query.data.replace("answer_", "")
    word = context.user_data.get("test_word")

    if not word:
        await query.message.reply_text("⚠️ Нет активного вопроса. Напиши /test снова.")
        return

    correct = word["en"]
    if selected == correct:
        msg = f"✅ Верно! {word['nl']} — {correct}"
    else:
        msg = f"❌ Неверно. {word['nl']} — {correct}, а не {selected}"

    await query.message.reply_text(msg)
    await query.message.reply_text(
        "Следующий вопрос?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧪 Новый вопрос", callback_data="new_test")]
        ])
    )

# --- Новый тест ---
async def new_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await start_test(update, context)

# --- /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — начать\n"
        "/progress — твой прогресс\n"
        "/test — проверка знаний\n"
        "Нажимай на кнопки под сообщениями, чтобы двигаться дальше."
    )

# --- Main ---
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("test", start_test))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CallbackQueryHandler(handle_word, pattern="^new_word$"))
    app.add_handler(CallbackQueryHandler(choose_topic, pattern="^topic_"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    app.add_handler(CallbackQueryHandler(new_test_question, pattern="^new_test$"))

    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
