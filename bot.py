import os
import sqlite3
import json
import tempfile
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from google import genai

TELEGRAM_BOT_TOKEN = "8603000098:AAF2-xVnJQmk7sbMBIbEiQ2LpPZqd4v6MSA"
GEMINI_API_KEY = "AQ.Ab8RN6Lt0DKOXKojc9OyqzZFGW5QfSHNIm8hnERg3aPmP0_HhA"
SECRET_PASSWORD = "4344"

client = genai.Client(api_key=GEMINI_API_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class AuthStates(StatesGroup):
    waiting_for_password = State()
    authenticated = State()

def init_db():
    conn = sqlite3.connect("finances.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            category TEXT,
            date TEXT,
            note TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_transaction(user_id, tx_type, amount, category, note=""):
    conn = sqlite3.connect("finances.db")
    cursor = conn.cursor()
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO transactions (user_id, type, amount, category, date, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, tx_type, amount, category, current_date, note))
    conn.commit()
    conn.close()

def get_user_transactions(user_id, limit=50):
    conn = sqlite3.connect("finances.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT type, amount, category, date, note FROM transactions 
        WHERE user_id = ? ORDER BY date DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(AuthStates.waiting_for_password)
    await message.answer("🔒 Цей бот захищений. Введіть пароль для доступу:")

@dp.message(AuthStates.waiting_for_password)
async def check_password(message: types.Message, state: FSMContext):
    if message.text == SECRET_PASSWORD:
        await state.set_state(AuthStates.authenticated)
        await message.answer(
            "✅ Авторизація успішна!\n\n"
            "▫️ Пиши витрати текстом (наприклад: *'кава 80'*)\n"
            "▫️ Надсилай голосові повідомлення\n"
            "▫️ Використовуй /ai_report для аналізу"
        )
    else:
        await message.answer("❌ Невірний пароль. Спробуйте ще раз:")

@dp.message(AuthStates.authenticated, F.text & ~F.text.startswith("/"))
async def handle_text_transaction(message: types.Message):
    await process_transaction_text(message, message.text)

@dp.message(AuthStates.authenticated, F.voice)
async def handle_voice_transaction(message: types.Message):
    await message.answer("🎙 Розпізнаю голосове повідомлення через Gemini...")
    file_info = await bot.get_file(message.voice.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        tmp.write(file_bytes.read())
        tmp_path = tmp.name

    try:
        audio_file = client.files.upload(file=tmp_path)
        prompt = (
            "Прослухай це аудіоповідомлення. Це опис фінансової транзакції. "
            "Визнач тип транзакції ('expense' або 'income'), суму (число), категорію та опис. "
            "Відповідь надай виключно у форматі JSON без жодних додаткових пояснень: "
            '{"type": "expense/income", "amount": 0.0, "category": "Категорія", "note": "опис"}'
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=[audio_file, prompt])
        client.files.delete(name=audio_file.name)
        
        raw_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        add_transaction(
            user_id=message.from_user.id,
            tx_type=data.get("type", "expense"),
            amount=float(data.get("amount", 0)),
            category=data.get("category", "Інше"),
            note=data.get("note", "Голосовий запис")
        )
        await message.answer(f"✅ Записано голосом!\nТип: {data.get('type')}\nСума: {data.get('amount')}\nКатегорія: {data.get('category')}")
    except Exception:
        await message.answer("⚠️ Не вдалося обробити голос.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

async def process_transaction_text(message: types.Message, user_text: str):
    prompt = (
        f"Проаналізуй текст: '{user_text}'. "
        "Визнач тип транзакції ('expense' або 'income'), суму (число), категорію та коментар. "
        "Формат JSON: {'type': 'expense/income', 'amount': 0.0, 'category': 'Категорія', 'note': 'опис'}"
    )
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw_json = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_json)
        
        add_transaction(
            user_id=message.from_user.id,
            tx_type=data.get("type", "expense"),
            amount=float(data.get("amount", 0)),
            category=data.get("category", "Інше"),
            note=data.get("note", user_text)
        )
        await message.answer(f"✅ Записано!\nСума: {data.get('amount')}\nКатегорія: {data.get('category')}")
    except Exception:
        await message.answer("⚠️ Не вдалося розпізнати транзакцію.")

@dp.message(AuthStates.authenticated, Command("ai_report"))
async def cmd_ai_report(message: types.Message):
    user_id = message.from_user.id
    txs = get_user_transactions(user_id, limit=100)
    if not txs:
        await message.answer("Немає транзакцій для аналізу.")
        return
    
    await message.answer("🧠 Аналізую витрати...")
    tx_history_str = "\n".join([f"- {t[3][:10]} | {t[0]}: {t[1]} ({t[2]})" for t in txs])
    prompt = f"Зроби аудит фінансів і дай поради українською:\n{tx_history_str}"
    
    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    await message.answer(response.text, parse_mode="Markdown")

@dp.message()
async def unauthenticated_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != AuthStates.authenticated.state:
        await message.answer("🔒 Будь ласка, введіть команду /start та вкажіть пароль.")

if __name__ == "__main__":
    init_db()
    print("Бот із паролем запущено...")
    dp.run_polling(bot)
