import sqlite3

def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            user_id INTEGER,
            word TEXT,
            PRIMARY KEY (user_id, word)
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def save_progress(user_id, word):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO progress (user_id, word) VALUES (?, ?)", (user_id, word))
    conn.commit()
    conn.close()

def get_progress(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM progress WHERE user_id = ?", (user_id,))
    result = cur.fetchone()[0]
    conn.close()
    return result

def get_user_count():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count