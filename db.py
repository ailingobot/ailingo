import sqlite3
import os

# Путь к базе данных — постоянное хранилище Render
DB_PATH = os.getenv("DB_PATH", "/mnt/data/bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS progress (
        user_id INTEGER,
        topic TEXT,
        word_index INTEGER,
        PRIMARY KEY (user_id, topic)
    )''')
    conn.commit()
    conn.close()


def get_user_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users


def save_progress(user_id, topic, word_index):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO progress (user_id, topic, word_index)
                 VALUES (?, ?, ?)''', (user_id, topic, word_index))
    conn.commit()
    conn.close()


def get_progress(user_id, topic):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT word_index FROM progress WHERE user_id = ? AND topic = ?''',
              (user_id, topic))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0
