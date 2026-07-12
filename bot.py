import os
import io
import csv
import logging
import sqlite3
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telebot.apihelper import ApiTelegramException

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN", "8818508524:AAGveS9f-dFVlsNvm1t9r6yWxzEEaDWSxjA")
LEAKOSINT_TOKEN = os.getenv("LEAKOSINT_TOKEN", "8250933960:1YyON0gP")
API_URL = "https://leakosintapi.com/"
CHANNEL_USERNAME = "@TraxFIND"
CHANNEL_LINK = "https://t.me/TraxFIND"
OWNER = "@traxvezz"

bot = telebot.TeleBot(BOT_TOKEN)
cache_reports = {}

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

    limit = 3000 if deep else 300
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
                lines.append("")
            text = "\n".join(lines)
            if len(text) > 3900:
                text = text[:3900] + "\n\n⚠️ <i>Обрезано</i>"
            reports.append(text)
        return reports, databases
    except Exception as e:
        logging.error(f"API error: {e}")
        return None, None

def make_keyboard(qid, page, total):
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []
    if total > 1:
        buttons.append(InlineKeyboardButton("◀", callback_data=f"p {qid} {page-1}"))
        buttons.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="no_action"))
        buttons.append(InlineKeyboardButton("▶", callback_data=f"p {qid} {page+1}"))
    buttons.append(InlineKeyboardButton("📥", callback_data=f"exp {qid}"))
    buttons.append(InlineKeyboardButton("⭐", callback_data=f"fav {qid}"))
    kb.add(*buttons)
    return kb

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("ФИО"), KeyboardButton("Всё"))
    kb.add(KeyboardButton("Глубоко"), KeyboardButton("История"))
    kb.add(KeyboardButton("★"), KeyboardButton("?"))
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    if not check_subscription(m.from_user.id):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK))
        kb.add(InlineKeyboardButton("🔄 Проверить", callback_data="check_sub"))
        bot.send_message(
            m.chat.id,
            f"Подпишись на канал:\n{CHANNEL_LINK}\n\nПосле подписки нажми «Проверить»",
            reply_markup=kb
        )
        return

    bot.send_message(
        m.chat.id,
        "TraxFIND\n\nПоиск по базам: ФИО, телефон, почта, логин.\nМеню внизу — просто выбери режим.\n\nИзбранное и история — чтобы не терять.\n\nВладелец: @traxvezz",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_sub_cb(c):
    if check_subscription(c.from_user.id):
        try:
            bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        bot.send_message(c.message.chat.id, "✅ Доступ открыт", reply_markup=main_menu())
        bot.answer_callback_query(c.id, "Подтверждено")
    else:
        bot.answer_callback_query(c.id, "❌ Не подписан", show_alert=True)

@bot.message_handler(func=lambda m: m.text == "?")
def help_cmd(m):
    if not check_subscription(m.from_user.id):
        return
    bot.send_message(m.chat.id,
        "ФИО — имя, фамилия\n"
        "Всё — телефон, почта, логин\n"
        "Глубоко — больше записей\n"
        "История — повтор запросов\n"
        "★ — сохранённое\n\n"
        f"{OWNER}")

@bot.message_handler(func=lambda m: m.text in ["ФИО", "Всё", "Глубоко"])
def set_mode(m):
    if not check_subscription(m.from_user.id):
        return
    mode = "fio" if m.text == "ФИО" else "all"
    deep = m.text == "Глубоко"
    bot.send_message(m.chat.id, f"{m.text}\nВведите запрос")
    bot.register_next_step_handler(m, lambda msg: process_query(msg, mode, deep))

@bot.message_handler(func=lambda m: m.text == "История")
def show_history_cmd(m):
    if not check_subscription(m.from_user.id):
        return
    hist = get_history(m.from_user.id)
    if not hist:
        bot.send_message(m.chat.id, "—")
        return
    lines = ["История:"]
    for i, q in enumerate(hist):
        lines.append(f"{i+1}. {q}")
    lines.append("\nВведите номер для повтора")
    bot.send_message(m.chat.id, "\n".join(lines))
    bot.register_next_step_handler(m, repeat_query)

def repeat_query(m):
    if not check_subscription(m.from_user.id):
        return
    try:
        idx = int(m.text.strip()) - 1
        hist = get_history(m.from_user.id)
        if 0 <= idx < len(hist):
            bot.send_message(m.chat.id, f"Повтор: {hist[idx]}")
            m.text = hist[idx]
            process_query(m, "all", False)
        else:
            bot.reply_to(m, "—")
    except ValueError:
        bot.reply_to(m, "—")

@bot.message_handler(func=lambda m: m.text == "★")
def show_favs_cmd(m):
    if not check_subscription(m.from_user.id):
        return
    favs = get_favorites(m.from_user.id)
    if not favs:
        bot.send_message(m.chat.id, "—")
        return
    lines = ["Избранное:"]
    for i, item in enumerate(favs):
        short = item[:40] + "..." if len(item) > 40 else item
        lines.append(f"{i+1}. {short}")
    lines.append("\nВведите номер для удаления")
    bot.send_message(m.chat.id, "\n".join(lines))
    bot.register_next_step_handler(m, delete_fav)

def delete_fav(m):
    if not check_subscription(m.from_user.id):
        return
    try:
        idx = int(m.text.strip()) - 1
        if delete_from_favorites(m.from_user.id, idx):
            bot.reply_to(m, "Удалено")
        else:
            bot.reply_to(m, "—")
    except ValueError:
        bot.reply_to(m, "—")

def process_query(m, mode, deep):
    if not check_subscription(m.from_user.id):
        return
    if not m.text or m.text.startswith("/"):
        bot.reply_to(m, "—")
        return

    add_to_history(m.from_user.id, m.text)
    status = bot.send_message(m.chat.id, "⏳")
    reports, databases = get_report(m.text, mode, deep)

    try:
        bot.delete_message(m.chat.id, status.message_id)
    except:
        pass

    if not reports:
        bot.send_message(m.chat.id, "—")
        return

    qid = f"{m.from_user.id}_{m.message_id}"
    cache_reports[qid] = {"reports": reports, "databases": databases, "query": m.text}

    try:
        bot.send_message(m.chat.id, reports[0], parse_mode="HTML", reply_markup=make_keyboard(qid, 0, len(reports)))
    except ApiTelegramException:
        clean = reports[0].replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","").replace("<code>","").replace("</code>","")
        bot.send_message(m.chat.id, clean, reply_markup=make_keyboard(qid, 0, len(reports)))

@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    if c.data == "no_action":
        bot.answer_callback_query(c.id)
        return

    parts = c.data.split()
    if len(parts) < 3:
        bot.answer_callback_query(c.id, "Ошибка")
        return

    action = parts[0]
    qid = parts[1]

    if qid not in cache_reports:
        bot.answer_callback_query(c.id, "Кеш устарел", show_alert=True)
        return

    session = cache_reports[qid]

    if action == "p":
        page = int(parts[2])
        reports = session["reports"]
        if 0 <= page < len(reports):
            try:
                bot.edit_message_text(
                    reports[page],
                    c.message.chat.id,
                    c.message.message_id,
                    parse_mode="HTML",
                    reply_markup=make_keyboard(qid, page, len(reports))
                )
            except ApiTelegramException:
                clean = reports[page].replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","").replace("<code>","").replace("</code>","")
                bot.edit_message_text(clean, c.message.chat.id, c.message.message_id, reply_markup=make_keyboard(qid, page, len(reports)))
            bot.answer_callback_query(c.id)

    elif action == "fav":
        if add_to_favorites(c.from_user.id, c.message.text):
            bot.answer_callback_query(c.id, "⭐ Сохранено")
        else:
            bot.answer_callback_query(c.id, "Уже есть", show_alert=True)

    elif action == "exp":
        bot.answer_callback_query(c.id, "⏳")
        databases = session["databases"]
        query = session["query"]

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Запрос", query])

        for db_name, db_content in databases.items():
            writer.writerow([])
            writer.writerow([f"Источник: {db_name}", db_content["info"]])
            if db_content["data"]:
                first = db_content["data"][0]
                headers = list(first.keys())
                writer.writerow(headers)
                for entry in db_content["data"]:
                    writer.writerow([entry.get(h, "") for h in headers])

        output.seek(0)
        bio = io.BytesIO(output.getvalue().encode("utf-8-sig"))
        bio.name = "report.csv"
        bot.send_document(c.message.chat.id, bio, caption="✅ Готово")

if __name__ == "__main__":
    logging.info("Запущен")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
