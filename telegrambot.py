import json
import os
import sqlite3
import logging
from datetime import datetime, time
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Налаштування логування для дебагу
logging.basicConfig(filename="bot.log", format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Шпаргалки (усі ваші нотатки)
NOTES = {
    "Прийом сервісного товару": """
📦 <b>Прийом сервісного товару зі складу (брак):</b>
1. ERP PL
2. Обробка → Створити переміщення
3. Звідки: [Вкажіть склад]
4. Дорога: Сервіс Львів Шувар
5. Скануємо товар → F7
""",
    "Заміна цінників": """
🏷️ <b>Заміна цінників (щоденна):</b>
1. ERP UA → Львів Шувар
2. Обробки → Друк цінників
3. Заповнити новими цінами
4. Надрукувати
""",
    "Друк цінників": """
🖨️ <b>Друк цінників:</b>
1. ERP UA → Львів Шувар
2. Обробки → Друк цінників
3. Вибрати товари → F9
4. Принтер: Зебра Шувар
""",
    "Перевірка наявності товару": """
🔍 <b>Перевірка наявності товару:</b>
1. ERP PL → Склад
2. Обробка → Залишки
3. Вводимо артикул → F5
4. Перевіряємо наявність
""",
    "Термін придатності": """
📅 <b>Перевірка терміну придатності:</b>
1. ERP UA → Львів Шувар
2. Залишки → Фільтр → Термін придатності
3. Вибрати товари, термін яких спливає
4. Сформувати звіт → F9
""",
    "Прийом товару (звичайний)": """
📥 <b>Прийом товару (звичайний):</b>
1. ERP PL → Приймання
2. Створити документ → Вказати постачальника
3. Скануємо товар через ТЗД
4. Перевіряємо кількість → F7
5. Підтверджуємо прийом
""",
    "Помилки при прийомі": """
❌ <b>Помилки при прийомі товару:</b>
1. Якщо товар не сканується:
   - Перевірити артикул у ERP PL
   - Зв’язатися з постачальником через Rocket Chat
2. Якщо кількість не співпадає:
   - Створити акт розбіжностей → ERP UA → Обробки
   - Вказати розбіжності → F9
""",
    "Перевірка надлишків": """
🔎 <b>Перевірка надлишків:</b>
1. ERP PL → Залишки
2. Обробка → Надлишки
3. Скануємо товар через ТЗД
4. Порівнюємо з даними ERP
5. Якщо є надлишки → Створити документ
""",
    "Товар після ремонту": """
🔧 <b>Товар після ремонту:</b>
1. ERP PL → Сервіс
2. Обробка → Повернення після ремонту
3. Скануємо серійний номер
4. Перевіряємо стан → F7
5. Відправляємо на склад
""",
    "Друк серійного номеру": """
🖨️ <b>Друк серійного номеру:</b>
1. ERP UA → Львів Шувар
2. Обробки → Друк серійних номерів
3. Вказати артикул → F9
4. Принтер: Зебра Шувар
""",
    "Сервісні звернення": """
📞 <b>Сервісні звернення:</b>
1. ERP PL → Сервіс
2. Створити звернення
3. Вказати проблему, артикул, серійний номер
4. Відправити в Rocket Chat (канал #service)
5. Чекати підтвердження
""",
    "Відгрузка надлишків": """
🚚 <b>Відгрузка/Повернення надлишків:</b>
<b>Швидке переміщення:</b>
1. ТЗД → Обробки → Швидке переміщення
2. Куди: Склад (Подол, Бровари, Бор, Подол ЛВІ)
3. Перевізник: Доставка → Кількість місць
4. Скануємо товар → Завершити
5. Принтер: Зебра Шувар

<b>Повернення надлишків:</b>
1. ПК → Обробка → Повернення надлишків
2. Вибираємо склад → Заповнити → Переміщаємо
3. ТЗД → Зборка → Скануємо товар → Зона відгрузки
4. Відвантаження → Пакування товарів → Скануємо товар
5. Перевіряємо (F9) → Завершити → Упакувати і списати
6. Принтер: Зебра Шувар
""",
    "Друк маркування": """
🏷️ <b>Друк маркування:</b>
1. ERP UA → Львів Шувар
2. Обробки → Друк маркування
3. Вибрати товар → Вказати кількість
4. Надрукувати → Принтер: Зебра Шувар
""",
    "Маркетплейс відгрузка": """
📦 <b>Маркетплейс відгрузка:</b>
1. ERP UA → Маркетплейс
2. Обробка → Відгрузка
3. Скануємо товар через ТЗД
4. Перевіряємо замовлення → F9
5. Упаковка → Доставка
"""
}

# Ініціалізація SQLite
def init_db():
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT,
                text TEXT,
                chat_id INTEGER,
                repeat TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                days TEXT
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO workdays (id, days) VALUES (1, ?)", (json.dumps([0, 1, 2, 3, 4]),))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
    finally:
        conn.close()

# Читання/збереження нагадувань
def load_reminders():
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT time, text, chat_id, repeat FROM reminders")
        reminders = [{"time": row[0], "text": row[1], "chat_id": row[2], "repeat": row[3]} for row in cursor.fetchall()]
        return reminders
    except Exception as e:
        logger.error(f"Failed to load reminders: {e}")
        return []
    finally:
        conn.close()

def save_reminders(reminders):
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders")
        for reminder in reminders:
            cursor.execute("INSERT INTO reminders (time, text, chat_id, repeat) VALUES (?, ?, ?, ?)",
                           (reminder["time"], reminder["text"], reminder["chat_id"], reminder.get("repeat")))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save reminders: {e}")
    finally:
        conn.close()

# Читання/збереження робочих днів
def load_workdays():
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT days FROM workdays WHERE id = 1")
        result = cursor.fetchone()
        return json.loads(result[0]) if result else [0, 1, 2, 3, 4]
    except Exception as e:
        logger.error(f"Failed to load workdays: {e}")
        return [0, 1, 2, 3, 4]
    finally:
        conn.close()

def save_workdays(workdays):
    try:
        conn = sqlite3.connect("bot_data.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE workdays SET days = ? WHERE id = 1", (json.dumps(workdays),))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save workdays: {e}")
    finally:
        conn.close()

# Перевірка робочого дня
def is_workday():
    today = datetime.now().weekday()
    workdays = load_workdays()
    return today in workdays

# Клавіатура
keyboard = [
    ["Прийом сервісного товару", "Заміна цінників", "Друк цінників"],
    ["Перевірка наявності товару", "Термін придатності", "Прийом товару (звичайний)"],
    ["Помилки при прийомі", "Перевірка надлишків", "Товар після ремонту"],
    ["Друк серійного номеру", "Сервісні звернення", "Відгрузка надлишків"],
    ["Друк маркування", "Маркетплейс відгрузка"],
    ["Нагадування", "Робочі дні"]
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_db()
    await update.message.reply_text(
        "👋 Привіт! Я твій помічник для роботи в Розетці. Обери тему шпаргалки або керуй нагадуваннями:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    logger.info(f"User {update.message.chat_id} started the bot")

async def reply_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"User {update.message.chat_id} requested note: {text}")
    if text == "Нагадування":
        keyboard = [
            [InlineKeyboardButton("08:00", callback_data="reminder_time_08:00"),
             InlineKeyboardButton("12:00", callback_data="reminder_time_12:00")],
            [InlineKeyboardButton("14:00", callback_data="reminder_time_14:00"),
             InlineKeyboardButton("18:00", callback_data="reminder_time_18:00")]
        ]
        await update.message.reply_text(
            "📅 Керуй нагадуваннями:\n"
            "/addreminder <час> <період> <текст> - Додати нагадування (HH:MM, період: daily/weekly)\n"
            "/delreminder <індекс> - Видалити нагадування\n"
            "/listreminders - Показати всі нагадування\n"
            "Або вибери час нижче:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif text == "Робочі дні":
        await update.message.reply_text(
            "📆 Вкажи робочі дні командою:\n"
            "/setworkdays <дні> (наприклад, 0 1 2 3 4 для Пн-Пт)"
        )
    else:
        note = NOTES.get(text)
        if note:
            if len(note) > 4096:
                for i in range(0, len(note), 4096):
                    await update.message.reply_text(note[i:i+4096], parse_mode="HTML")
            else:
                await update.message.reply_text(note, parse_mode="HTML")
        else:
            matches = [key for key in NOTES if text.lower() in key.lower()]
            if matches:
                response = "📋 Знайдені шпаргалки:\n" + "\n".join(matches)
                await update.message.reply_text(response)
            else:
                await update.message.reply_text("🤔 Не знайшов такої шпаргалки. Спробуй ще раз!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Я бот для шпаргалок по роботі в Розетці. Вибери тему з меню, керуй нагадуваннями або напиши /start."
    )
    logger.info(f"User {update.message.chat_id} used /help")

async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("📝 Вкажи час, період (daily/weekly) і текст: /addreminder HH:MM daily Текст")
        return
    try:
        reminder_time = time.fromisoformat(args[0])
        repeat = args[1].lower()
        if repeat not in ["daily", "weekly"]:
            await update.message.reply_text("❌ Період: daily або weekly")
            return
        text = " ".join(args[2:])
        reminders = load_reminders()
        reminders.append({
            "time": args[0],
            "repeat": repeat,
            "text": text,
            "chat_id": update.message.chat_id
        })
        save_reminders(reminders)
        await update.message.reply_text(f"✅ Нагадування додано: {args[0]} ({repeat}) - {text}")
        logger.info(f"User {update.message.chat_id} added reminder: {args[0]} ({repeat}) - {text}")
    except ValueError:
        await update.message.reply_text("❌ Неправильний формат часу. Використовуй HH:MM")

async def del_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("📝 Вкажи індекс: /delreminder <індекс>")
        return
    try:
        index = int(args[0])
        reminders = load_reminders()
        if 0 <= index < len(reminders):
            removed = reminders.pop(index)
            save_reminders(reminders)
            await update.message.reply_text(f"🗑️ Нагадування видалено: {removed['time']} - {removed['text']}")
            logger.info(f"User {update.message.chat_id} deleted reminder: {removed['time']} - {removed['text']}")
        else:
            await update.message.reply_text("❌ Неправильний індекс")
    except ValueError:
        await update.message.reply_text("❌ Вкажи число як індекс")

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = load_reminders()
    if not reminders:
        await update.message.reply_text("📅 Нагадувань немає")
        return
    response = "📋 Список нагадувань:\n"
    for i, reminder in enumerate(reminders):
        repeat = reminder.get("repeat", "одноразове")
        response += f"{i}: {reminder['time']} ({repeat}) - {reminder['text']}\n"
    await update.message.reply_text(response)
    logger.info(f"User {update.message.chat_id} listed reminders")

async def set_workdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("📆 Вкажи дні (0-6, де 0 - Пн): /setworkdays 0 1 2 3 4")
        return
    try:
        workdays = [int(day) for day in args if 0 <= int(day) <= 6]
        save_workdays(workdays)
        await update.message.reply_text(f"✅ Робочі дні встановлено: {workdays}")
        logger.info(f"User {update.message.chat_id} set workdays: {workdays}")
    except ValueError:
        await update.message.reply_text("❌ Вкажи числа від 0 до 6")

async def pin_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key, note in NOTES.items():
        await update.message.reply_text(note, parse_mode="HTML")
    await update.message.reply_text("📌 Закріпи ці повідомлення для офлайн-доступу!")
    logger.info(f"User {update.message.chat_id} used /pinnotes")

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("reminder_time_"):
        context.user_data["reminder_time"] = query.data.replace("reminder_time_", "")
        await query.message.reply_text("📝 Введи текст нагадування та період (daily/weekly):")
        context.user_data["awaiting_reminder_text"] = True
        logger.info(f"User {query.message.chat_id} selected reminder time: {context.user_data['reminder_time']}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_reminder_text"):
        text = update.message.text.split()
        if len(text) < 2:
            await update.message.reply_text("📝 Вкажи період (daily/weekly) і текст: період Текст")
            return
        repeat = text[0].lower()
        if repeat not in ["daily", "weekly"]:
            await update.message.reply_text("❌ Період: daily або weekly")
            return
        reminder_text = " ".join(text[1:])
        reminder_time = context.user_data.get("reminder_time")
        try:
            time.fromisoformat(reminder_time)
            reminders = load_reminders()
            reminders.append({
                "time": reminder_time,
                "text": reminder_text,
                "chat_id": update.message.chat_id,
                "repeat": repeat
            })
            save_reminders(reminders)
            await update.message.reply_text(f"✅ Нагадування додано: {reminder_time} ({repeat}) - {reminder_text}")
            logger.info(f"User {update.message.chat_id} added reminder via inline: {reminder_time} ({repeat}) - {reminder_text}")
            context.user_data["awaiting_reminder_text"] = False
            context.user_data["reminder_time"] = None
        except ValueError:
            await update.message.reply_text("❌ Помилка часу. Спробуй ще раз.")
    else:
        await reply_note(update, context)

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    if not is_workday():
        return
    now = datetime.now()
    current_time = now.time().strftime("%H:%M")
    reminders = load_reminders()
    for reminder in reminders:
        if reminder["time"] == current_time:
            if reminder.get("repeat") == "daily" or (
                reminder.get("repeat") == "weekly" and
                (reminder.get("last_triggered") is None or
                 (now - datetime.fromisoformat(reminder["last_triggered"])).days >= 7)
            ):
                try:
                    await context.bot.send_message(
                        chat_id=reminder["chat_id"],
                        text=f"⏰ Нагадування: {reminder['text']}"
                    )
                    logger.info(f"Sent reminder to {reminder['chat_id']}: {reminder['time']} - {reminder['text']}")
                    if reminder.get("repeat") == "weekly":
                        reminder["last_triggered"] = now.isoformat()
                except Exception as e:
                    logger.error(f"Failed to send reminder to {reminder['chat_id']}: {e}")
    save_reminders(reminders)

def main():
    init_db()
    token = os.environ.get("BOT_TOKEN", "8099873828:AAGT3L40FQcpkT4ubgPMpi8hzpZwG_xJsF0")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addreminder", add_reminder))
    app.add_handler(CommandHandler("delreminder", del_reminder))
    app.add_handler(CommandHandler("listreminders", list_reminders))
    app.add_handler(CommandHandler("setworkdays", set_workdays))
    app.add_handler(CommandHandler("pinnotes", pin_notes))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Періодична перевірка нагадувань
    if app.job_queue:
        app.job_queue.run_repeating(check_reminders, interval=60, first=0)
    else:
        logger.error("JobQueue is not available. Please install python-telegram-bot[job-queue].")
    
    # Використовуємо polling для локального тестування, Webhook для продакшену
    if os.environ.get("RENDER"):
        port = int(os.environ.get("PORT", 8443))
        webhook_url = os.environ.get("WEBHOOK_URL")
        if not webhook_url:
            logger.error("WEBHOOK_URL is not set")
            raise ValueError("WEBHOOK_URL is not set")
        try:
            app.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path="/bot",
                webhook_url=f"{webhook_url}/bot"
            )
            logger.info(f"Webhook started on {webhook_url}/bot")
        except Exception as e:
            logger.error(f"Failed to start webhook: {e}")
            raise
    else:
        try:
            app.run_polling()
            logger.info("Polling started for local testing")
        except Exception as e:
            logger.error(f"Failed to start polling: {e}")
            raise

if __name__ == "__main__":
    main()
