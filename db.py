import sqlite3
import os
import datetime

# Путь к базе данных — постоянное хранилище Render
DB_PATH = os.getenv("DB_PATH", "/mnt/data/bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Создание таблицы с новыми полями, если она ещё не создана
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date TEXT,
            country TEXT,
            left INTEGER DEFAULT 0
        )
    ''')

    # Проверка и добавление недостающих колонок
    existing_columns = [row[1] for row in c.execute("PRAGMA table_info(users)")]
    if 'join_date' not in existing_columns:
        c.execute("ALTER TABLE users ADD COLUMN join_date TEXT")
    if 'country' not in existing_columns:
        c.execute("ALTER TABLE users ADD COLUMN country TEXT")
    if 'left' not in existing_columns:
        c.execute("ALTER TABLE users ADD COLUMN left INTEGER DEFAULT 0")

    c.execute('''CREATE TABLE IF NOT EXISTS progress (
        user_id INTEGER,
        topic TEXT,
        word_index INTEGER,
        PRIMARY KEY (user_id, topic)
    )''')

    conn.commit()
    conn.close()

def add_user(user_id, username, country=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, join_date, country) VALUES (?, ?, ?, ?)",
              (user_id, username, datetime.date.today().isoformat(), country))
    conn.commit()
    conn.close()

def mark_user_left(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET left = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_current_users_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE left = 0")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_left_users_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE left = 1")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_new_users_by_day():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT join_date, COUNT(*) 
        FROM users 
        WHERE left = 0
        GROUP BY join_date 
        ORDER BY join_date DESC
    """)
    result = c.fetchall()
    conn.close()
    return result

def get_new_users_by_week():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT strftime('%Y-%W', join_date) as week, COUNT(*) 
        FROM users 
        WHERE left = 0
        GROUP BY week
        ORDER BY week DESC
    """)
    result = c.fetchall()
    conn.close()
    return result

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

def get_country_statistics():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT country, COUNT(*) FROM users
        WHERE left = 0 AND country IS NOT NULL
        GROUP BY country
        ORDER BY COUNT(*) DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return rows
