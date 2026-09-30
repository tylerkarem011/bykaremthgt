import asyncio
import os
import random

import aiosqlite
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
DB = "queue.db"

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

async def init_db():
    async with aiosqlite.connect(DB) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                message_id INTEGER,
                mode TEXT
            )
        """)

        await db.commit()


async def get_user(user_id):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT name FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()


async def get_users():
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT user_id, name FROM users ORDER BY name"
        )
        return await cursor.fetchall()


async def get_queue():
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("""
            SELECT q.user_id, u.name
            FROM queue q
            JOIN users u ON q.user_id = u.user_id
            ORDER BY q.id
        """)
        return await cursor.fetchall()


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
        member = await bot.get_chat_member(chat_id, user_id)

        return member.status in ("administrator", "creator")

    except Exception:
        return False


# =========================
# QUEUE TEXT
# =========================

async def queue_text(mode="free"):

    queue = await get_queue()

    if mode == "random":
        title = "🎲 <b>СЛУЧАЙНАЯ ОЧЕРЕДЬ</b>"
    else:
        title = "📝 <b>СВОБОДНАЯ ОЧЕРЕДЬ</b>"

    text = f"🎓 {title}\n\n"

    if not queue:
        text += "📭 <b>Очередь пока пустая.</b>\n\n"
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
    text += f"👥 Всего в очереди: <b>{len(queue)}</b>"

    return text


# =========================
# UPDATE MESSAGE
# =========================

async def save_message(chat_id, message_id, mode):

    async with aiosqlite.connect(DB) as db:

        await db.execute("""
            INSERT INTO settings (chat_id, message_id, mode)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id)
            DO UPDATE SET
                message_id = excluded.message_id,
                mode = excluded.mode
        """, (chat_id, message_id, mode))

        await db.commit()


async def get_mode(chat_id):

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute(
            "SELECT mode FROM settings WHERE chat_id = ?",
            (chat_id,)
        )

        result = await cursor.fetchone()

        return result[0] if result else "free"


async def update_queue_message(chat_id):

    async with aiosqlite.connect(DB) as db:

        cursor = await db.execute(
            "SELECT message_id, mode FROM settings WHERE chat_id = ?",
            (chat_id,)
        )

        result = await cursor.fetchone()

    if not result:
        return

    message_id, mode = result

    try:

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=await queue_text(mode),
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )

    except Exception:
        pass


# =========================
# START / REGISTRATION
# =========================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):

    # Регистрация только в личке
    if message.chat.type != "private":
        await message.answer(
            "👋 Чтобы зарегистрироваться, напиши мне /start в личных сообщениях."
        )
        return

    user = await get_user(message.from_user.id)

    if user:

        await message.answer(
            f"👋 Привет, <b>{user[0]}</b>!\n\n"
            "✅ Ты уже зарегистрирован.\n"
            "Теперь можешь участвовать в очереди.",
            parse_mode="HTML"
        )

        return

    await message.answer(
        "🎓 <b>Добро пожаловать!</b>\n\n"
        "Для начала введи своё имя и фамилию.\n\n"
        "Например:\n"
        "<i>Карим Байнашов</i>",
        parse_mode="HTML"
    )

    await state.set_state(Registration.waiting_name)


@dp.message(Registration.waiting_name)
async def save_name(message: Message, state: FSMContext):

    name = message.text.strip()

    if len(name) < 2:
        await message.answer("❌ Напиши нормальное имя и фамилию.")
        return

    async with aiosqlite.connect(DB) as db:

        await db.execute(
            "INSERT INTO users (user_id, name) VALUES (?, ?)",
            (message.from_user.id, name)
        )

        await db.commit()

    await state.clear()

    await message.answer(
        f"✅ <b>Готово!</b>\n\n"
        f"Тебя зарегистрировали как:\n"
        f"👤 <b>{name}</b>\n\n"
        "Теперь ты можешь участвовать в очереди группы.",
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
        await message.answer("❌ Только для администраторов.")
        return

    await message.answer(
        "🛡 <b>ПАНЕЛЬ УЧИТЕЛЯ</b>\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# =========================
# CREATE QUEUE MESSAGE
# =========================

@dp.message(Command("queue"))
async def create_queue(message: Message):

    if not await is_admin(
        message.chat.id,
        message.from_user.id
    ):
        await message.answer(
            "❌ Только учитель/администратор может создать очередь."
        )
        return

    msg = await message.answer(
        await queue_text("free"),
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

    await save_message(
        message.chat.id,
        msg.message_id,
        "free"
    )


# =========================
# JOIN QUEUE
# =========================

@dp.callback_query(F.data == "join")
async def join_queue(callback: CallbackQuery):

    user = await get_user(callback.from_user.id)

    if not user:

        await callback.answer(
            "❌ Сначала зарегистрируйся через /start в личке с ботом.",
            show_alert=True
        )
        return

    queue = await get_queue()

    # Уже в очереди?
    for user_id, _ in queue:

        if user_id == callback.from_user.id:

            position = next(
                i for i, x in enumerate(queue, 1)
                if x[0] == callback.from_user.id
            )

            await callback.answer(
                f"⚠️ Ты уже в очереди! Позиция: №{position}",
                show_alert=True
            )

            return

    # Добавляем
    async with aiosqlite.connect(DB) as db:

        await db.execute(
            "INSERT INTO queue (user_id) VALUES (?)",
            (callback.from_user.id,)
        )

        await db.commit()

    queue = await get_queue()

    position = len(queue)

    await callback.answer(
        f"✅ Ты в очереди! Позиция: №{position}",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# MY POSITION
# =========================

@dp.callback_query(F.data == "position")
async def position(callback: CallbackQuery):

    queue = await get_queue()

    for number, (user_id, name) in enumerate(queue, 1):

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
# SHOW QUEUE
# =========================

@dp.callback_query(F.data == "show")
async def show_queue(callback: CallbackQuery):

    mode = await get_mode(callback.message.chat.id)

    await callback.answer()

    try:
        await callback.message.edit_text(
            await queue_text(mode),
            parse_mode="HTML",
            reply_markup=main_keyboard()
        )
    except Exception:
        pass


# =========================
# ADMIN: RANDOM
# =========================

@dp.callback_query(F.data == "random")
async def random_queue(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только учитель может рандомизировать.",
            show_alert=True
        )
        return

    users = await get_users()

    if not users:

        await callback.answer(
            "❌ Пока никто не зарегистрирован.",
            show_alert=True
        )
        return

    random.shuffle(users)

    async with aiosqlite.connect(DB) as db:

        await db.execute("DELETE FROM queue")

        for user_id, _ in users:

            await db.execute(
                "INSERT INTO queue (user_id) VALUES (?)",
                (user_id,)
            )

        await db.commit()

        await db.execute("""
            UPDATE settings
            SET mode = ?
            WHERE chat_id = ?
        """, ("random", callback.message.chat.id))

        await db.commit()

    await callback.answer(
        "🎲 Очередь случайно сформирована!",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# ADMIN: FREE QUEUE
# =========================

@dp.callback_query(F.data == "free")
async def free_queue(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только учитель может менять режим.",
            show_alert=True
        )
        return

    async with aiosqlite.connect(DB) as db:

        await db.execute(
            "DELETE FROM queue"
        )

        await db.execute("""
            UPDATE settings
            SET mode = ?
            WHERE chat_id = ?
        """, ("free", callback.message.chat.id))

        await db.commit()

    await callback.answer(
        "📝 Включена свободная очередь!",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# ADMIN: DONE
# =========================

@dp.callback_query(F.data == "done")
async def done(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только для учителя.",
            show_alert=True
        )
        return

    queue = await get_queue()

    if not queue:

        await callback.answer(
            "📭 Очередь пустая.",
            show_alert=True
        )
        return

    user_id, name = queue[0]

    async with aiosqlite.connect(DB) as db:

        await db.execute(
            "DELETE FROM queue WHERE user_id = ?",
            (user_id,)
        )

        await db.commit()

    await callback.answer(
        f"✅ {name} сдал!",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# ADMIN: SKIP
# =========================

@dp.callback_query(F.data == "skip")
async def skip(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только для учителя.",
            show_alert=True
        )
        return

    queue = await get_queue()

    if not queue:

        await callback.answer(
            "📭 Очередь пустая.",
            show_alert=True
        )
        return

    user_id, name = queue[0]

    async with aiosqlite.connect(DB) as db:

        await db.execute(
            "DELETE FROM queue WHERE user_id = ?",
            (user_id,)
        )

        await db.commit()

    await callback.answer(
        f"⏭ {name} пропущен.",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# ADMIN: RESET
# =========================

@dp.callback_query(F.data == "reset")
async def reset(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только для учителя.",
            show_alert=True
        )
        return

    async with aiosqlite.connect(DB) as db:

        await db.execute("DELETE FROM queue")

        await db.commit()

    await callback.answer(
        "🔄 Очередь очищена!",
        show_alert=True
    )

    await update_queue_message(callback.message.chat.id)


# =========================
# ADMIN: STUDENTS
# =========================

@dp.callback_query(F.data == "students")
async def students(callback: CallbackQuery):

    if not await is_admin(
        callback.message.chat.id,
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Только для учителя.",
            show_alert=True
        )
        return

    users = await get_users()

    if not users:

        await callback.answer(
            "📭 Никто ещё не зарегистрирован.",
            show_alert=True
        )
        return

    text = "👥 <b>ЗАРЕГИСТРИРОВАННЫЕ УЧЕНИКИ</b>\n\n"

    for number, (_, name) in enumerate(users, 1):

        text += f"{number}. {name}\n"

    await callback.message.answer(
        text,
        parse_mode="HTML"
    )

    await callback.answer()


# =========================
# MAIN
# =========================

async def main():

    await init_db()

    print("🤖 Бот запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())