import asyncio
import os
import random

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не найден")

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================
# РЕГИСТРАЦИЯ
# =========================

class Registration(StatesGroup):
    waiting_name = State()


# =========================
# DATABASE
# =========================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id BIGINT PRIMARY KEY,
            message_id BIGINT,
            mode TEXT DEFAULT 'free'
        )
    """)

    db.commit()
    cursor.close()
    db.close()


def get_user(user_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT name FROM users WHERE user_id = %s",
        (user_id,)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return result


def get_users():
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT user_id, name FROM users ORDER BY name"
    )

    result = cursor.fetchall()

    cursor.close()
    db.close()

    return result


def get_queue():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT q.user_id, u.name
        FROM queue q
        JOIN users u ON q.user_id = u.user_id
        ORDER BY q.id
    """)

    result = cursor.fetchall()

    cursor.close()
    db.close()

    return result


# =========================
# KEYBOARDS
# =========================

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Встать в очередь",
                    callback_data="join"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📍 Моя позиция",
                    callback_data="position"
                ),
                InlineKeyboardButton(
                    text="📋 Очередь",
                    callback_data="show"
                )
            ]
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎲 Рандом",
                    callback_data="random"
                ),
                InlineKeyboardButton(
                    text="📝 Свободная",
                    callback_data="free"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Сдал",
                    callback_data="done"
                ),
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="skip"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Ученики",
                    callback_data="students"
                ),
                InlineKeyboardButton(
                    text="🔄 Сбросить",
                    callback_data="reset"
                )
            ]
        ]
    )


# =========================
# ADMIN CHECK
# =========================

async def is_admin(chat_id, user_id):

    try:
        member = await bot.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in (
            "administrator",
            "creator"
        )

    except Exception:
        return False


# =========================
# MODE
# =========================

def get_mode(chat_id):

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT mode FROM settings WHERE chat_id = %s",
        (chat_id,)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    if result:
        return result[0]

    return "free"


def set_mode(chat_id, mode):

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO settings (chat_id, mode)
        VALUES (%s, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET mode = EXCLUDED.mode
    """, (chat_id, mode))

    db.commit()

    cursor.close()
    db.close()


# =========================
# QUEUE MESSAGE
# =========================

def queue_text(mode):

    queue = get_queue()

    if mode == "random":
        title = "🎲 <b>СЛУЧАЙНАЯ ОЧЕРЕДЬ</b>"
    else:
        title = "📝 <b>СВОБОДНАЯ ОЧЕРЕДЬ</b>"

    text = f"🎓 {title}\n\n"

    if not queue:

        text += "📭 <b>Очередь пока пустая.</b>\n\n"

        if mode == "free":
            text += "Нажмите кнопку ниже, чтобы встать в очередь."

        return text

    text += "━━━━━━━━━━━━━━━━━━\n"

    for number, (_, name) in enumerate(queue, start=1):

        if number == 1:
            text += f"🟢 <b>1. {name}</b> ← сейчас\n"

        elif number == 2:
            text += f"🥈 <b>2. {name}</b>\n"

        elif number == 3:
            text += f"🥉 <b>3. {name}</b>\n"

        else:
            text += f"{number}. {name}\n"

    text += "━━━━━━━━━━━━━━━━━━\n"
    text += f"👥 Всего: <b>{len(queue)}</b>"

    return text


# =========================
# SAVE MAIN MESSAGE
# =========================

def save_message(chat_id, message_id, mode):

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO settings (chat_id, message_id, mode)
        VALUES (%s, %s, %s)

        ON CONFLICT (chat_id)
        DO UPDATE SET
            message_id = EXCLUDED.message_id,
            mode = EXCLUDED.mode
    """, (chat_id, message_id, mode))

    db.commit()

    cursor.close()
    db.close()


def get_message_id(chat_id):

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT message_id FROM settings WHERE chat_id = %s",
        (chat_id,)
    )

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return result[0] if result else None


async def update_queue_message(chat_id):

    message_id = get_message_id(chat_id)

    if not message_id:
        return

    mode = get_mode(chat_id)

    try:

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=queue_text(mode),
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        if "message is not modified" not in str(e):
            print("Ошибка обновления сообщения:", e)


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):

    if message.chat.type != "private":

        await message.answer(
            "👋 Для регистрации открой личку со мной и напиши /start"
        )

        return

    user = get_user(message.from_user.id)

    if user:

        await message.answer(
            f"👋 Привет, <b>{user[0]}</b>!\n\n"
            "✅ Ты уже зарегистрирован.",
            parse_mode="HTML"
        )

        return

    await message.answer(
        "🎓 <b>Добро пожаловать!</b>\n\n"
        "Введи своё имя и фамилию.\n\n"
        "Например:\n"
        "<i>Карим Байнашов</i>",
        parse_mode="HTML"
    )

    await state.set_state(
        Registration.waiting_name
    )


# =========================
# SAVE NAME
# =========================

@dp.message(Registration.waiting_name)
async def save_name(message: Message, state: FSMContext):

    name = message.text.strip()

    if len(name) < 2:

        await message.answer(
            "❌ Введи имя и фамилию."
        )

        return

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO users (user_id, name)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET name = EXCLUDED.name
    """, (
        message.from_user.id,
        name
    ))

    db.commit()

    cursor.close()
    db.close()

    await state.clear()

    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 {name}\n\n"
        "Теперь ты можешь участвовать в очереди.",
        parse_mode="HTML"
    )


# =========================
# ADMIN PANEL
# =========================

@dp.message(Command("admin"))
async def admin_panel(message: Message):

    if not await is_admin(
        message.chat.id,
        message.from_user.id
    ):

        await message.answer(
            "❌ Только для администраторов группы."
        )

        return

    await message.answer(
        "🛡 <b>ПАНЕЛЬ УЧИТЕЛЯ</b>\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# =========================
# CREATE QUEUE
# =========================

@dp.message(Command("queue"))
async def create_queue(message: Message):

    if not await is_admin(
        message.chat.id,
        message.from_user.id
    ):

        await message.answer(
            "❌ Только учитель может создать очередь."
        )

        return

    mode = "free"

    set_mode(
        message.chat.id,
        mode
    )

    msg = await message.answer(
        queue_text(mode),
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

    save_message(
        message.chat.id,
        msg.message_id,
        mode
    )


# =========================
# JOIN
# =========================

@dp.callback_query(F.data == "join")
async def join_queue(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    mode = get_mode(chat_id)

    if mode == "random":

        await callback.answer(
            "🎲 Сейчас действует случайная очередь.",
            show_alert=True
        )

        return

    user = get_user(
        callback.from_user.id
    )

    if not user:

        await callback.answer(
            "❌ Сначала зарегистрируйся через /start в личке.",
            show_alert=True
        )

        return

    queue = get_queue()

    for user_id, _ in queue:

        if user_id == callback.from_user.id:

            position = next(
                i for i, item in enumerate(queue, 1)
                if item[0] == callback.from_user.id
            )

            await callback.answer(
                f"⚠️ Ты уже в очереди! №{position}",
                show_alert=True
            )

            return

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "INSERT INTO queue (user_id) VALUES (%s)",
        (callback.from_user.id,)
    )

    db.commit()

    cursor.close()
    db.close()

    position = len(queue) + 1

    await callback.answer(
        f"✅ Ты в очереди! Позиция №{position}",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# POSITION
# =========================

@dp.callback_query(F.data == "position")
async def position(callback: CallbackQuery):

    queue = get_queue()

    for number, (user_id, _) in enumerate(
        queue,
        start=1
    ):

        if user_id == callback.from_user.id:

            await callback.answer(
                f"📍 Ты №{number} в очереди.",
                show_alert=True
            )

            return

    await callback.answer(
        "❌ Тебя сейчас нет в очереди.",
        show_alert=True
    )


# =========================
# SHOW
# =========================

@dp.callback_query(F.data == "show")
async def show_queue(callback: CallbackQuery):

    mode = get_mode(
        callback.message.chat.id
    )

    await callback.answer()

    try:

        await callback.message.edit_text(
            queue_text(mode),
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )

    except Exception as e:

        if "message is not modified" not in str(e):
            print("Ошибка:", e)


# =========================
# RANDOM
# =========================

@dp.callback_query(F.data == "random")
async def random_queue(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    if not await is_admin(
        chat_id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    users = get_users()

    if not users:

        await callback.answer(
            "❌ Пока никто не зарегистрирован.",
            show_alert=True
        )

        return

    users = list(users)

    random.shuffle(users)

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM queue"
    )

    for user_id, _ in users:

        cursor.execute(
            "INSERT INTO queue (user_id) VALUES (%s)",
            (user_id,)
        )

    db.commit()

    cursor.close()
    db.close()

    set_mode(
        chat_id,
        "random"
    )

    await callback.answer(
        f"🎲 Готово! Перемешано {len(users)} учеников.",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# FREE
# =========================

@dp.callback_query(F.data == "free")
async def free_queue(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    if not await is_admin(
        chat_id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM queue"
    )

    db.commit()

    cursor.close()
    db.close()

    set_mode(
        chat_id,
        "free"
    )

    await callback.answer(
        "📝 Свободная очередь включена!",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# DONE
# =========================

@dp.callback_query(F.data == "done")
async def done(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    if not await is_admin(
        chat_id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    queue = get_queue()

    if not queue:

        await callback.answer(
            "📭 Очередь пустая.",
            show_alert=True
        )

        return

    user_id, name = queue[0]

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM queue WHERE user_id = %s",
        (user_id,)
    )

    db.commit()

    cursor.close()
    db.close()

    await callback.answer(
        f"✅ {name} сдал!",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# SKIP
# =========================

@dp.callback_query(F.data == "skip")
async def skip(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    if not await is_admin(
        chat_id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    queue = get_queue()

    if not queue:

        await callback.answer(
            "📭 Очередь пустая.",
            show_alert=True
        )

        return

    user_id, name = queue[0]

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM queue WHERE user_id = %s",
        (user_id,)
    )

    db.commit()

    cursor.close()
    db.close()

    await callback.answer(
        f"⏭ {name} пропущен.",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# RESET
# =========================

@dp.callback_query(F.data == "reset")
async def reset(callback: CallbackQuery):

    chat_id = callback.message.chat.id

    if not await is_admin(
        chat_id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM queue"
    )

    db.commit()

    cursor.close()
    db.close()

    await callback.answer(
        "🔄 Очередь очищена!",
        show_alert=True
    )

    await update_queue_message(chat_id)


# =========================
# STUDENTS
# =========================

@dp.callback_query(F.data == "students")
async def students(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):

        await callback.answer(
            "❌ Только учитель.",
            show_alert=True
        )

        return

    users = get_users()

    if not users:

        await callback.answer(
            "📭 Никто не зарегистрирован.",
            show_alert=True
        )

        return

    text = "👥 <b>УЧЕНИКИ</b>\n\n"

    for number, (_, name) in enumerate(
        users,
        start=1
    ):

        text += f"{number}. {name}\n"

    await callback.message.answer(
        text,
        parse_mode="HTML"
    )

    await callback.answer()


# =========================
# START BOT
# =========================

async def main():

    init_db()

    print("🤖 Бот запущен!")
    print("🗄 PostgreSQL подключена!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())