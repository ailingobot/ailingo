
import sqlite3

def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS progress (user_id INTEGER, topic TEXT, word_index INTEGER)"
    )
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def save_progress(user_id, topic, word_index):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO progress (user_id, topic, word_index) VALUES (?, ?, ?)", (user_id, topic, word_index))
    conn.commit()
    conn.close()

def get_progress(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT topic, word_index FROM progress WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result if result else (None, 0)

def get_user_count():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]
