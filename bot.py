import os
import io
import csv
import logging
import sqlite3
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN", "8818508524:AAGveS9f-dFVlsNvm1t9r6yWxzEEaDWSxjA")
LEAKOSINT_TOKEN = os.getenv("LEAKOSINT_TOKEN", "8250933960:1YyON0gP")
API_URL = "https://leakosintapi.com"
CHANNEL_USERNAME = "@TraxFIND"
CHANNEL_LINK = "https://t.me"
OWNER = "@traxvezz"

bot = telebot.TeleBot(BOT_TOKEN)
cache = {}

def init_db():
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                user_id TEXT, query TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT, item TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_db()

LOCAL_DB = [
    {
        "База": "2GIS 2025",
        "Инфо": "Профили по телефонам России и Казахстана",
        "Данные": [
            {"ФИО": "Алексей Дивановский", "Ссылка": "2gis.ru/user/7296eded5ee14dbdb87a1f3abf0ae45e", "Телефон": "+79503938712"}
        ]
    }
]

def add_to_history(user_id, query):
    with sqlite3.connect("bot_database.db") as conn:
        conn.cursor().execute("INSERT INTO history (user_id, query) VALUES (?, ?)", (str(user_id), query))

def get_history(user_id):
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT query FROM history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (str(user_id),))
        return [row[0] for row in reversed(cursor.fetchall())]

def add_to_favorites(user_id, item):
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND item = ?", (str(user_id), item))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO favorites (user_id, item) VALUES (?, ?)", (str(user_id), item))
            return True
        return False

def get_favorites(user_id):
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT item FROM favorites WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20", (str(user_id),))
        return [row[0] for row in cursor.fetchall()]

def delete_from_favorites(user_id, index):
    with sqlite3.connect("bot_database.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ROWID, item FROM favorites WHERE user_id = ? ORDER BY timestamp DESC", (str(user_id),))
        rows = cursor.fetchall()
        if 0 <= index < len(rows):
            cursor.execute("DELETE FROM favorites WHERE ROWID = ?", (rows[index][0],))
            return rows[index][1]
        return None

def check_subscription(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def search_local(query):
    results = []
    q = query.lower().strip()
    for db in LOCAL_DB:
        for entry in db["Данные"]:
            if q in entry.get("ФИО", "").lower() or q in entry.get("Телефон", "").lower():
                results.append((db["База"], db["Инфо"], entry))
    return results

def get_report(query, search_type="all", deep=False):
    local_results = search_local(query)
    if local_results:
        reports, databases = [], {}
        for db_name, info, entry in local_results:
            lines = [f"📋 <b>Источник: {db_name}</b>", f"<i>{info}</i>", ""]
            for field, value in entry.items():
                lines.append(f"<b>{field}:</b> <code>{value}</code>")
            reports.append("\n".join(lines))
            databases[db_name] = {"info": info, "data": [entry]}
        return reports, databases

    if search_type == "fio":
        parts = query.strip().split()
        if len(parts) >= 2:
            query = " ".join(parts[:3])

    limit = 5000 if deep else 300
    payload = {"token": LEAKOSINT_TOKEN, "request": query, "limit": limit, "lang": "ru"}

    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        resp_data = response.json()

        if "Error code" in resp_data:
            return None, None

        databases = {}
        for db_name, db_content in resp_data.get("List", {}).items():
            if db_name == "No results found" or not db_content.get("Data"):
                continue
            databases[db_name] = {
                "info": db_content.get("InfoLeak", "Описание отсутствует"),
                "data": db_content.get("Data", [])
            }

        if not databases:
            return None, None

        reports = []
        for db_name, db_content in databases.items():
            lines = [f"📋 <b>Источник: {db_name}</b>", f"<i>{db_content['info']}</i>", ""]
            
            for entry in db_content["data"]:
                for field, value in entry.items():
                    if value and str(value).strip():
                        lines.append(f"<b>{field}:</b> <code>{value}</code>")
                lines.append("•")  # Лаконичный и аккуратный разделитель записей
            
            if lines[-1] == "•":
                lines.pop()
                
            text = "\n".join(lines)
            if len(text) > 3900:
                text = text[:3900] + "\n\n⚠️ <i>Данные частично обрезаны...</i>"
            reports.append(text)

        return reports, databases
    except Exception as e:
        logging.error(f"API request error: {e}")
        return None, None

def make_keyboard(qid, page, total):
    kb = InlineKeyboardMarkup(row_width=3)
    if total > 1:
        kb.add(
            InlineKeyboardButton("◀️ Назад", callback_data=f"p {qid} {page-1}"),
            InlineKeyboardButton(f"{page+1} из {total}", callback_data="no_action"),
            InlineKeyboardButton("Вперед ▶️", callback_data=f"p {qid} {page+1}")
        )
    kb.row(
        InlineKeyboardButton("📥 Скачать CSV", callback_data=f"exp {qid}"),
        InlineKeyboardButton("⭐ В избранное", callback_data=f"fav {qid}")
    )
    return kb

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("👤 Поиск по ФИО"), KeyboardButton("🌐 Поиск: Всё"))
    kb.add(KeyboardButton("🔎 Глубокий поиск"), KeyboardButton("📜 История запросов"))
    kb.add(KeyboardButton("⭐ Избранное"), KeyboardButton("❓ Справка"))
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    if not check_subscription(m.from_user.id):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_sub")]
        ])
        bot.send_message(
            m.chat.id,
            f"🤖 <b>Добро пожаловать в TraxFIND!</b>\n\nДля получения доступа к поиску подпишитесь на наш официальный канал:\n{CHANNEL_LINK}",
            parse_mode="HTML", reply_markup=kb
        )
        return
    bot.send_message(m.chat.id, "🦅 <b>TraxFIND</b> готов к работе. Выберите режим поиска в меню ниже:", parse_mode="HTML", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_sub_cb(c):
    if check_subscription(c.from_user.id):
        try:
            bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        bot.send_message(c.message.chat.id, "✅ <b>Доступ открыт!</b> Выберите режим поиска:", parse_mode="HTML", reply_markup=main_menu())
        bot.answer_callback_query(c.id, "Доступ разрешен")
    else:
        bot.answer_callback_query(c.id, "❌ Вы не подписались на канал!", show_alert=True)

@bot.message_handler(func=lambda m: m.text in ["❓ Справка", "?"])
def help_cmd(m):
    if not check_subscription(m.from_user.id): return
    bot.send_message(m.chat.id, 
        "💡 <b>Режимы поиска TraxFIND:</b>\n\n"
        "• <b>Поиск по ФИО</b> — Поиск по совпадениям Имени и Фамилии.\n"
        "• <b>Поиск: Всё</b> — Универсальный запрос (телефон, email, логины, авто).\n"
        "• <b>Глубокий поиск</b> — Расширенный поиск с лимитом выдачи до 5000 строк.\n"
        "• <b>История запросов</b> — Просмотр и перезапуск последних 10 поисков.\n"
        "• <b>Избранное</b> — Сохраненные вами результаты.\n\n"
        f"👔 Разработчик: {OWNER}", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text in ["👤 Поиск по ФИО", "🌐 Поиск: Всё", "🔎 Глубокий поиск"])
def set_mode(m):
    if not check_subscription(m.from_user.id): return
    mode = "fio" if "ФИО" in m.text else "all"
    deep = "Глубокий" in m.text
    msg = bot.send_message(m.chat.id, "📥 Введите ваш поисковый запрос:")
    bot.register_next_step_handler(msg, lambda target_msg: process_query(target_msg, mode, deep))

@bot.message_handler(func=lambda m: m.text == "📜 История запросов")
def show_history_cmd(m):
    if not check_subscription(m.from_user.id): return
    hist = get_history(m.from_user.id)
    if not hist:
        bot.send_message(m.chat.id, "📭 История запросов пуста.")
        return
    lines = ["<b>📜 Ваши последние запросы:</b>\n"]
    for i, q in enumerate(hist):
        lines.append(f"{i+1}. <code>{q}</code>")
    lines.append("\n🔢 <i>Отправьте номер строки, чтобы повторить поиск.</i>")
    msg = bot.send_message(m.chat.id, "\n".join(lines), parse_mode="HTML")
    bot.register_next_step_handler(msg, repeat_query)

def repeat_query(m):
    if not check_subscription(m.from_user.id): return
