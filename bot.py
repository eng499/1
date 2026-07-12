import requests
import telebot
import csv
import io
import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8818508524:AAGveS9f-dFVlsNvm1t9r6yWxzEEaDWSxjA"
LEAKOSINT_TOKEN = "8250933960:1YyON0gP"
LANG = "ru"
LIMIT = 300
DEEP_LIMIT = 5000
API_URL = "https://leakosintapi.com/"
OWNER = "@traxvezz"

bot = telebot.TeleBot(BOT_TOKEN)
cache = {}
history = {}
favorites = {}

def get_report(query, search_type="all", deep=False):
    if search_type == "fio":
        parts = query.strip().split()
        if len(parts) >= 2:
            query = " ".join(parts[:3])
    
    limit = DEEP_LIMIT if deep else LIMIT
    data = {"token": LEAKOSINT_TOKEN, "request": query, "limit": limit, "lang": LANG}
    
    try:
        resp = requests.post(API_URL, json=data, timeout=30).json()
        if "Error code" in resp:
            return None, None
        
        databases = {}
        for db_name, db_content in resp.get("List", {}).items():
            if db_name == "No results found":
                continue
            databases[db_name] = {"info": db_content.get("InfoLeak", ""), "data": db_content.get("Data", [])}
        
        if not databases:
            return None, None
        
        reports = []
        for db_name, db_content in databases.items():
            lines = [f"<b>{db_name}</b>", db_content["info"], "─" * 40]
            for entry in db_content["data"]:
                for field, value in entry.items():
                    if value and str(value).strip():
                        lines.append(f"<b>{field}</b>: {value}")
                lines.append("")
            text = "\n".join(lines)
            if len(text) > 3500:
                text = text[:3500] + text[3500:].split("\n")[0] + "\n\nОбрезано"
            reports.append(text)
        return reports, databases
    except:
        return None, None

def make_keyboard(qid, page, total):
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []
    if total > 1:
        buttons.append(InlineKeyboardButton("◀", callback_data=f"p {qid} {page-1}"))
        buttons.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="no"))
        buttons.append(InlineKeyboardButton("▶", callback_data=f"p {qid} {page+1}"))
    buttons.append(InlineKeyboardButton("Экспорт", callback_data=f"exp {qid}"))
    buttons.append(InlineKeyboardButton("Сохранить", callback_data=f"fav {qid}"))
    buttons.append(InlineKeyboardButton("Фильтр", callback_data=f"fil {qid}"))
    kb.add(*buttons)
    return kb

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("Поиск по ФИО"), KeyboardButton("Поиск по всему"))
    kb.add(KeyboardButton("Глубокий поиск"), KeyboardButton("История"))
    kb.add(KeyboardButton("Избранное"), KeyboardButton("Помощь"))
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    user_id = str(m.from_user.id)
    if user_id not in history:
        history[user_id] = []
    if user_id not in favorites:
        favorites[user_id] = []
    bot.send_message(m.chat.id, f"Привет! Owner: {OWNER}", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "Помощь")
def help_cmd(m):
    bot.send_message(m.chat.id, 
        "Поиск по ФИО - только имя/фамилия\n"
        "Поиск по всему - email, телефон, логин\n"
        "Глубокий поиск - лимит 5000\n"
        "История - последние 10 запросов\n"
        "Избранное - сохранённые записи\n"
        "Экспорт - скачать CSV\n"
        "Фильтр - выбрать базу\n"
        f"Owner: {OWNER}")

@bot.message_handler(func=lambda m: m.text in ["Поиск по ФИО", "Поиск по всему", "Глубокий поиск"])
def set_mode(m):
    mode = "fio" if "ФИО" in m.text else "all"
    deep = "Глубокий" in m.text
    bot.send_message(m.chat.id, f"Режим: {'ФИО' if mode == 'fio' else 'Всё'}{' (глубокий)' if deep else ''}\nОтправь запрос.")
    bot.register_next_step_handler(m, lambda msg: process_query(msg, mode, deep))

@bot.message_handler(func=lambda m: m.text == "История")
def show_history(m):
    user_id = str(m.from_user.id)
    if user_id not in history or not history[user_id]:
        bot.send_message(m.chat.id, "История пуста.")
        return
    hist = "\n".join([f"{i+1}. {q}" for i, q in enumerate(history[user_id][-10:])])
    bot.send_message(m.chat.id, f"Последние запросы:\n\n{hist}\n\nВведи номер для повтора.")
    bot.register_next_step_handler(m, repeat_query)

def repeat_query(m):
    try:
        idx = int(m.text) - 1
        user_id = str(m.from_user.id)
        if idx < 0 or idx >= len(history[user_id]):
            bot.reply_to(m, "Неверный номер.")
            return
        query = history[user_id][idx]
        bot.reply_to(m, f"Повтор: {query}")
        process_query(m, "all", False)
    except:
        bot.reply_to(m, "Введи число.")

@bot.message_handler(func=lambda m: m.text == "Избранное")
def show_favs(m):
    user_id = str(m.from_user.id)
    if user_id not in favorites or not favorites[user_id]:
        bot.send_message(m.chat.id, "Избранное пусто.")
        return
    favs = "\n".join([f"{i+1}. {item}" for i, item in enumerate(favorites[user_id][-20:])])
    bot.send_message(m.chat.id, f"Избранное:\n\n{favs}\n\nВведи номер для удаления.")
    bot.register_next_step_handler(m, delete_fav)

def delete_fav(m):
    try:
        idx = int(m.text) - 1
        user_id = str(m.from_user.id)
        if idx < 0 or idx >= len(favorites[user_id]):
            bot.reply_to(m, "Неверный номер.")
            return
        removed = favorites[user_id].pop(idx)
        bot.reply_to(m, f"Удалено: {removed}")
    except:
        bot.reply_to(m, "Введи число.")

def process_query(m, mode, deep):
    if not m.text:
        bot.reply_to(m, "Отправь текст.")
        return
    
    user_id = str(m.from_user.id)
    if user_id not in history:
        history[user_id] = []
    history[user_id].append(m.text)
    
    qid = f"{user_id}_{m.message_id}"
    reports, databases = get_report(m.text, mode, deep)
    
    if not reports:
        bot.reply_to(m, "Ничего не найдено.")
        return
    
    cache[qid] = {"reports": reports, "databases": databases}
    kb = make_keyboard(qid, 0, len(reports))
    try:
        bot.send_message(m.chat.id, reports[0], parse_mode="HTML", reply_markup=kb)
    except:
        bot.send_message(m.chat.id, reports[0].replace("<b>","").replace("</b>",""), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("p "))
def page_cb(c):
    _, qid, p = c.data.split()
    p = int(p)
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Кеш устарел")
        return
    reports = data["reports"]
    if p < 0:
        p = len(reports) - 1
    elif p >= len(reports):
        p = 0
    kb = make_keyboard(qid, p, len(reports))
    try:
        bot.edit_message_text(reports[p], c.message.chat.id, c.message.message_id, parse_mode="HTML", reply_markup=kb)
    except:
        bot.edit_message_text(reports[p].replace("<b>","").replace("</b>",""), c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("exp "))
def export_cb(c):
    qid = c.data.split()[1]
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Данных нет")
        return
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["База", "Инфо", "Поле", "Значение"])
    for db_name, db_data in data["databases"].items():
        for entry in db_data["data"]:
            for field, value in entry.items():
                writer.writerow([db_name, db_data["info"], field, value])
    
    file = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    bot.send_document(c.chat.id, ("data.csv", file), caption="Экспорт")
    bot.answer_callback_query(c.id, "Готово")

@bot.callback_query_handler(func=lambda c: c.data.startswith("fav "))
def fav_cb(c):
    qid = c.data.split()[1]
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Данных нет")
        return
    
    user_id = str(c.from_user.id)
    for db_name, db_data in data["databases"].items():
        if db_data["data"]:
            entry = db_data["data"][0]
            item = f"{db_name}: " + ", ".join([f"{k}={v}" for k, v in entry.items()])
            favorites[user_id].append(item)
            bot.answer_callback_query(c.id, f"Сохранено")
            return
    bot.answer_callback_query(c.id, "Нет данных")

@bot.callback_query_handler(func=lambda c: c.data.startswith("fil "))
def filter_cb(c):
    qid = c.data.split()[1]
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Данных нет")
        return
    
    db_list = list(data["databases"].keys())
    kb = InlineKeyboardMarkup(row_width=2)
    for i, db in enumerate(db_list):
        kb.add(InlineKeyboardButton(db[:30], callback_data=f"fs {qid} {i}"))
    kb.add(InlineKeyboardButton("Назад", callback_data=f"fb {qid}"))
    bot.send_message(c.message.chat.id, "Выбери базу:", reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("fs "))
def filter_select_cb(c):
    _, qid, idx = c.data.split()
    idx = int(idx)
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Данных нет")
        return
    
    db_list = list(data["databases"].keys())
    if idx >= len(db_list):
        bot.answer_callback_query(c.id, "Ошибка")
        return
    
    db_name = db_list[idx]
    db_data = data["databases"][db_name]
    
    lines = [f"<b>{db_name}</b>", db_data["info"], "─" * 40]
    for entry in db_data["data"]:
        for field, value in entry.items():
            if value and str(value).strip():
                lines.append(f"<b>{field}</b>: {value}")
        lines.append("")
    text = "\n".join(lines)
    bot.send_message(c.message.chat.id, text, parse_mode="HTML")
    bot.answer_callback_query(c.id, f"Показано: {db_name}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("fb "))
def filter_back_cb(c):
    qid = c.data.split()[1]
    data = cache.get(qid)
    if not data:
        bot.answer_callback_query(c.id, "Данных нет")
        return
    kb = make_keyboard(qid, 0, len(data["reports"]))
    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=kb)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "no")
def no_cb(c):
    bot.answer_callback_query(c.id, "Страница")

print("Бот запущен")
bot.infinity_polling()
