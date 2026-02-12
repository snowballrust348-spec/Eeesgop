import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, FSInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Создайте файл .env: BOT_TOKEN=ваш_токен")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ADMIN_SECRET_CODE = "2305"

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            photo_id TEXT NOT NULL,
            is_available BOOLEAN DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            user_full_name TEXT,
            city TEXT NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            user_full_name TEXT,
            message TEXT NOT NULL,
            reply_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_answered BOOLEAN DEFAULT 0
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        test_products = [
            ("Платье 'Летнее'", "Легкое летнее платье из хлопка, размеры S-M-L", 349, "Женская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Джинсы 'Slim Fit'", "Классические джинсы прямого кроя, размеры 42-54", 429, "Женская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Футболка 'Oversize'", "Удобная футболка свободного кроя, размеры S-XXL", 199, "Женская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Кроссовки 'Urban'", "Стильные повседневные кроссовки, размеры 36-45", 599, "Обувь", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Сумка 'Тотализатор'", "Вместительная сумка из экокожи", 399, "Аксессуары", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Рубашка 'Classic'", "Элегантная рубашка из хлопка, размеры S-XXL", 299, "Мужская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Худи 'Comfort'", "Уютное худи из флиса, размеры S-XXL", 379, "Мужская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
            ("Шорты 'Casual'", "Легкие шорты для повседневной носки, размеры 46-56", 249, "Мужская одежда", "AgACAgIAAxkBAAIBX2cZQYqJZQZQZQZQZQZQZQZQZQZQZQZQ"),
        ]
        cursor.executemany(
            "INSERT INTO products (name, description, price, category, photo_id) VALUES (?, ?, ?, ?, ?)",
            test_products
        )
    
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_admin(user_id: int, username: str, full_name: str):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO admins (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name)
    )
    conn.commit()
    conn.close()

def remove_admin(user_id: int):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

class OrderStates(StatesGroup):
    waiting_for_city = State()
    confirming_order = State()

class AdminStates(StatesGroup):
    waiting_for_admin_code = State()
    waiting_for_support_message_id = State()
    waiting_for_support_reply = State()
    waiting_for_product_name = State()
    waiting_for_product_description = State()
    waiting_for_product_price = State()
    waiting_for_product_category = State()
    waiting_for_product_photo = State()
    waiting_for_delete_product = State()
    waiting_for_delete_confirm = State()

class SupportStates(StatesGroup):
    waiting_for_message = State()

def get_main_menu():
    kb = [
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="🛒 Корзина")],
        [KeyboardButton(text="ℹ️ О нас"), KeyboardButton(text="📞 Контакты")],
        [KeyboardButton(text="🔐 Админка")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_menu():
    kb = [
        [KeyboardButton(text="➕ Добавить товар"), KeyboardButton(text="🗑 Удалить товар")],
        [KeyboardButton(text="📦 Заказы"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📨 Поддержка"), KeyboardButton(text="⬅️ Выйти из админки")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def format_price(amount):
    return f"{amount:.0f} BYN"

def get_categories():
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM products WHERE is_available = 1")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return categories

def categories_keyboard():
    kb = InlineKeyboardBuilder()
    for category in get_categories():
        kb.button(text=category, callback_data=f"category_{category}")
    kb.adjust(2)
    return kb.as_markup()

def products_keyboard(category, page=0):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    offset = page * 5
    cursor.execute(
        "SELECT id, name, price FROM products WHERE category = ? AND is_available = 1 LIMIT 5 OFFSET ?",
        (category, offset)
    )
    products = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM products WHERE category = ? AND is_available = 1", (category,))
    total = cursor.fetchone()[0]
    conn.close()

    kb = InlineKeyboardBuilder()
    for product_id, name, price in products:
        kb.button(text=f"{name} — {format_price(price)}", callback_data=f"product_{product_id}_{category}")

    if page > 0:
        kb.button(text="← Пред", callback_data=f"category_page_{category}_{page-1}")
    if offset + 5 < total:
        kb.button(text="След →", callback_data=f"category_page_{category}_{page+1}")

    kb.button(text="🛒 Корзина", callback_data="view_cart")
    kb.button(text="← К категориям", callback_data="back_to_categories")
    kb.adjust(1)
    return kb.as_markup()

def product_detail_keyboard(product_id, in_cart=False, category=None):
    kb = InlineKeyboardBuilder()
    if in_cart:
        kb.button(text="✅ В корзине", callback_data="in_cart")
    else:
        kb.button(text="🛒 Добавить в корзину", callback_data=f"add_to_cart_{product_id}")
    
    # КРИТИЧЕСКИ ВАЖНО: передаём категорию в callback_data для мобильного клиента
    if category:
        kb.button(text="← К товарам", callback_data=f"back_to_category_{category}")
    else:
        kb.button(text="← К категориям", callback_data="back_to_categories")
    
    kb.button(text="🛒 Корзина", callback_data="view_cart")
    kb.adjust(1)
    return kb.as_markup()

def cart_keyboard(cart_items):
    kb = InlineKeyboardBuilder()
    for item_id, product_name, quantity, price in cart_items:
        kb.button(text=f"❌ {product_name}", callback_data=f"remove_from_cart_{item_id}")
    if cart_items:
        kb.button(text="✅ Оформить заказ", callback_data="checkout")
        kb.button(text="🔄 Очистить корзину", callback_data="clear_cart")
    kb.button(text="← К категориям", callback_data="back_to_categories")
    kb.adjust(1)
    return kb.as_markup()

def get_user_cart(user_id):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cart.id, products.name, cart.quantity, products.price
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = ?
    ''', (user_id,))
    cart_items = cursor.fetchall()
    conn.close()
    return cart_items

# ===== ПРИВЕТСТВИЕ С ЛОКАЛЬНЫМ GIF welcome.gif =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    try:
        gif = FSInputFile("welcome.gif")
        await message.answer_animation(
            animation=gif,
            caption="✨ <b>Добро пожаловать в ENDORFINA!</b> ✨\n\n"
                    "🔥 Более 500+ довольных клиентов по странам СНГ!\n"
                    "👕 Премиальная одежда с доставкой в любую точку СНГ\n"
                    "💎 Стиль, который говорит за вас!\n\n"
                    "Выберите раздел ниже 👇",
            parse_mode="HTML"
        )
    except FileNotFoundError:
        await message.answer(
            "✨ <b>Добро пожаловать в ENDORFINA!</b> ✨\n\n"
            "🔥 Более 500+ довольных клиентов по странам СНГ!\n"
            "👕 Премиальная одежда с доставкой в любую точку СНГ\n"
            "💎 Стиль, который говорит за вас!\n\n"
            "Выберите раздел ниже 👇",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Ошибка отправки GIF: {e}")
        await message.answer(
            "✨ <b>Добро пожаловать в ENDORFINA!</b> ✨\n\n"
            "🔥 Более 500+ довольных клиентов по странам СНГ!\n"
            "👕 Премиальная одежда с доставкой в любую точку СНГ\n"
            "💎 Стиль, который говорит за вас!\n\n"
            "Выберите раздел ниже 👇",
            parse_mode="HTML"
        )
    
    if is_admin(message.from_user.id):
        await message.answer("👑 <b>Режим администратора</b>", reply_markup=get_admin_menu(), parse_mode="HTML")
    else:
        await message.answer("Меню:", reply_markup=get_main_menu())

# ===== ВХОД В АДМИНКУ =====
@dp.message(F.text == "🔐 Админка")
async def admin_login(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        await message.answer("👑 Вы уже в админ-режиме!", reply_markup=get_admin_menu())
        return
    await message.answer("🔐 Введите секретный код для входа в админку:")
    await state.set_state(AdminStates.waiting_for_admin_code)

@dp.message(AdminStates.waiting_for_admin_code)
async def check_admin_code(message: types.Message, state: FSMContext):
    if message.text.strip() == ADMIN_SECRET_CODE:
        add_admin(message.from_user.id, message.from_user.username, message.from_user.full_name)
        await message.answer("✅ Добро пожаловать в админ-панель!", reply_markup=get_admin_menu())
        logger.info(f"Новый админ: {message.from_user.full_name} (@{message.from_user.username})")
    else:
        await message.answer("❌ Неверный код!", reply_markup=get_main_menu())
    await state.clear()

@dp.message(F.text == "⬅️ Выйти из админки")
async def admin_logout(message: types.Message):
    if is_admin(message.from_user.id):
        remove_admin(message.from_user.id)
        await message.answer("🔓 Вы вышли из админ-режима", reply_markup=get_main_menu())
    else:
        await message.answer("Вы не в админ-режиме", reply_markup=get_main_menu())

# ===== УДАЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "🗑 Удалить товар")
async def delete_product_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category FROM products WHERE is_available = 1 ORDER BY category, name")
    products = cursor.fetchall()
    conn.close()
    
    if not products:
        await message.answer("📭 Нет доступных товаров для удаления", reply_markup=get_admin_menu())
        return
    
    text = "<b>🗑 Выберите товар для удаления:</b>\n\n"
    for pid, name, category in products:
        text += f"🆔 <code>{pid}</code> | {category} — {name}\n"
    
    text += "\n✏️ Введите ID товара для удаления:"
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_delete_product)

@dp.message(AdminStates.waiting_for_delete_product)
async def confirm_delete_product(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        product_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число:")
        return
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, category, photo_id FROM products WHERE id = ? AND is_available = 1", (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product:
        await message.answer("❌ Товар с таким ID не найден или уже удалён. Введите другой ID:")
        return
    
    name, category, photo_id = product
    await state.update_data(delete_product_id=product_id, delete_product_name=name, delete_product_category=category)
    
    text = f"❓ <b>Подтвердите удаление товара:</b>\n\nКатегория: {category}\nТовар: {name}\n\n⚠️ Товар будет скрыт из каталога. Удалить?"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, удалить", callback_data="confirm_delete_product")
    kb.button(text="❌ Отмена", callback_data="cancel_delete_product")
    kb.adjust(2)
    
    if photo_id and photo_id.startswith("AgAC"):
        await message.answer_photo(photo_id, caption=text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    
    await state.set_state(AdminStates.waiting_for_delete_confirm)

@dp.callback_query(F.data == "confirm_delete_product")
async def execute_delete_product(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    data = await state.get_data()
    product_id = data.get('delete_product_id')
    name = data.get('delete_product_name')
    
    if not product_id:
        await callback.message.edit_text("❌ Ошибка: данные для удаления утеряны", reply_markup=get_admin_menu())
        await state.clear()
        return
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET is_available = 0 WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"✅ Товар «{name}» успешно удалён из каталога!",
        reply_markup=get_admin_menu()
    )
    await callback.answer("Товар удалён!", show_alert=True)
    await state.clear()

@dp.callback_query(F.data == "cancel_delete_product")
async def cancel_delete_product(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Удаление отменено", reply_markup=get_admin_menu())
    await callback.answer()
    await state.clear()

# ===== ПОДДЕРЖКА ЧЕРЕЗ /support =====
@dp.message(Command("support"))
async def support_start(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        conn = sqlite3.connect('endorfina.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, username, user_full_name, message, created_at 
            FROM support_messages 
            WHERE is_answered = 0 
            ORDER BY created_at DESC 
            LIMIT 15
        ''')
        messages = cursor.fetchall()
        conn.close()

        if not messages:
            await message.answer("📭 Нет новых сообщений", reply_markup=get_admin_menu())
            return

        text = "<b>📨 Новые сообщения от клиентов:</b>\n\n"
        for msg_id, user_id, username, full_name, msg_text, created_at in messages:
            created_date = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m %H:%M")
            text += f"🆔 <b>#{msg_id}</b> | 👤 {full_name} (@{username or f'id{user_id}'})\n🕗 {created_date}\n💬 {msg_text[:70]}...\n\n"

        kb = InlineKeyboardBuilder()
        kb.button(text="✏️ Ответить", callback_data="support_reply")
        kb.button(text="🔄 Обновить", callback_data="refresh_support")
        kb.adjust(2)
        
        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer(
            "💬 <b>Напишите ваш вопрос в поддержку:</b>\n\n"
            "• Проблема с заказом?\n"
            "• Вопрос по товару?\n"
            "• Другое?\n\n"
            "Менеджер ответит вам в течение нескольких часов.",
            parse_mode="HTML"
        )
        await state.set_state(SupportStates.waiting_for_message)

@dp.message(SupportStates.waiting_for_message)
async def save_support_message(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO support_messages (user_id, username, user_full_name, message)
        VALUES (?, ?, ?, ?)
    ''', (message.from_user.id, message.from_user.username, message.from_user.full_name, message.text))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    conn.close()

    for admin in admins:
        try:
            await bot.send_message(
                admin[0],
                f"📨 <b>Новое сообщение #{msg_id}</b>\n👤 {message.from_user.full_name} (@{message.from_user.username})\n💬 {message.text}",
                parse_mode="HTML"
            )
        except:
            pass

    await message.answer("✅ Сообщение отправлено! Менеджер ответит вам скоро.", reply_markup=get_main_menu())
    await state.clear()

@dp.callback_query(F.data == "support_reply")
async def support_reply_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    await callback.message.answer("✏️ Введите ID сообщения для ответа (цифра после #):")
    await state.set_state(AdminStates.waiting_for_support_message_id)
    await callback.answer()

@dp.message(AdminStates.waiting_for_support_message_id)
async def get_message_id_for_reply(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        msg_id = int(message.text)
        conn = sqlite3.connect('endorfina.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, user_full_name, message FROM support_messages WHERE id = ? AND is_answered = 0",
            (msg_id,)
        )
        support_msg = cursor.fetchone()
        conn.close()

        if not support_msg:
            await message.answer("❌ Сообщение не найдено или уже отвечено. Введите другой ID:")
            return

        user_id, username, full_name, user_message = support_msg
        await state.update_data(reply_user_id=user_id, support_msg_id=msg_id)
        
        await message.answer(
            f"📨 <b>Ответ для:</b> {full_name} (@{username or f'id{user_id}'})\n\n"
            f"<b>Сообщение клиента:</b>\n{user_message}\n\n"
            "✏️ Напишите ответ:",
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.waiting_for_support_reply)

    except ValueError:
        await message.answer("❌ Введите корректный номер (только цифры):")

@dp.message(AdminStates.waiting_for_support_reply)
async def send_reply_to_client(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    user_id = data.get('reply_user_id')
    msg_id = data.get('support_msg_id')

    if not user_id or not msg_id:
        await message.answer("❌ Ошибка данных. Вернитесь в поддержку и выберите сообщение заново.", reply_markup=get_admin_menu())
        await state.clear()
        return

    reply_text = (
        "💬 <b>Ответ от поддержки ENDORFINA:</b>\n\n"
        f"{message.text}\n\n"
        "С уважением, команда ENDORFINA 💎"
    )

    try:
        await bot.send_message(user_id, reply_text, parse_mode="HTML")
        
        conn = sqlite3.connect('endorfina.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE support_messages SET is_answered = 1, reply_message = ? WHERE id = ?", (message.text, msg_id))
        conn.commit()
        conn.close()

        await message.answer("✅ Ответ успешно отправлен клиенту!", reply_markup=get_admin_menu())
        logger.info(f"Админ {message.from_user.id} ответил на сообщение #{msg_id} пользователю {user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки ответа клиенту {user_id}: {e}")
        await message.answer(
            "❌ Не удалось отправить ответ (пользователь заблокировал бота или удалил чат).",
            reply_markup=get_admin_menu()
        )

    await state.clear()

@dp.callback_query(F.data == "refresh_support")
async def refresh_support_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, user_id, username, user_full_name, message, created_at 
        FROM support_messages 
        WHERE is_answered = 0 
        ORDER BY created_at DESC 
        LIMIT 15
    ''')
    messages = cursor.fetchall()
    conn.close()

    text = "<b>📨 Сообщения (обновлено):</b>\n\n" if messages else "📭 Нет новых сообщений"
    for msg_id, user_id, username, full_name, msg_text, created_at in messages:
        created_date = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m %H:%M")
        text += f"🆔 <b>#{msg_id}</b> | 👤 {full_name} (@{username or f'id{user_id}'})\n🕗 {created_date}\n💬 {msg_text[:70]}...\n\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Ответить", callback_data="support_reply")
    kb.button(text="🔄 Обновить", callback_data="refresh_support")
    kb.adjust(2)
    
    await callback.message.edit_text(text or "📭 Нет новых сообщений", parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer("Обновлено ✅")

# ===== РАЗДЕЛЫ "О НАС" И "КОНТАКТЫ" =====
@dp.message(F.text == "ℹ️ О нас")
async def about_us(message: types.Message):
    text = (
        "✨ <b>ENDORFINA — премиум одежда</b> ✨\n\n"
        "🔥 Более 500+ довольных клиентов по странам СНГ!\n"
        "👕 Эксклюзивные коллекции, качественные ткани\n"
        "🚚 Доставка по всем городам СНГ (3–7 дней)\n"
        "🔄 Возврат в течение 14 дней\n\n"
        "👤 Наша команда:\n"
        "▫️ CEO / Владелец: @Imm0rtalMikha\n"
        "▫️ Dep CEO / Зам. владельца: @DrxnKid"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())

@dp.message(F.text == "📞 Контакты")
async def contacts(message: types.Message):
    text = (
        "📱 <b>Свяжитесь с нами только в Telegram:</b>\n\n"
        "▫️ <b>CEO / Владелец</b>\n   @Imm0rtalMikha\n\n"
        "▫️ <b>Dep CEO / Зам. владельца</b>\n   @DrxnKid\n\n"
        "⏰ Режим работы: ежедневно 10:00–22:00\n"
        "📍 Доставка: по всем городам СНГ"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())

# ===== СТАТИСТИКА =====
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products WHERE is_available = 1")
    products = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders")
    orders = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_amount) FROM orders")
    sales = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM support_messages WHERE is_answered = 0")
    pending = cursor.fetchone()[0]
    conn.close()

    text = (
        "📊 <b>Статистика ENDORFINA</b>\n\n"
        f"📦 Товаров: {products}\n"
        f"🛍️ Заказов: {orders}\n"
        f"💰 Продаж: {sales:.0f} BYN\n"
        f"📨 Новых сообщений: {pending}"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())

# ===== ДОБАВЛЕНИЕ ТОВАРА =====
@dp.message(F.text == "➕ Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("✏️ Название товара:")
    await state.set_state(AdminStates.waiting_for_product_name)

@dp.message(AdminStates.waiting_for_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📝 Описание:")
    await state.set_state(AdminStates.waiting_for_product_description)

@dp.message(AdminStates.waiting_for_product_description)
async def add_product_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("💰 Цена в BYN:")
    await state.set_state(AdminStates.waiting_for_product_price)

@dp.message(AdminStates.waiting_for_product_price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        await state.update_data(price=price)
        await message.answer("🏷 Категория (Женская одежда/Мужская одежда/Обувь/Аксессуары):")
        await state.set_state(AdminStates.waiting_for_product_category)
    except:
        await message.answer("❌ Введите корректную цену:")

@dp.message(AdminStates.waiting_for_product_category)
async def add_product_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await message.answer("📸 Отправьте фото товара:")
    await state.set_state(AdminStates.waiting_for_product_photo)

@dp.message(AdminStates.waiting_for_product_photo)
async def add_product_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Отправьте фото:")
        return
    
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, category, photo_id) VALUES (?, ?, ?, ?, ?)",
        (data['name'], data['description'], data['price'], data['category'], photo_id)
    )
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Товар «{data['name']}» добавлен за {data['price']:.0f} BYN", reply_markup=get_admin_menu())
    await state.clear()

# ===== ЗАКАЗЫ =====
@dp.message(F.text == "📦 Заказы")
async def show_orders(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_full_name, username, city, total_amount, created_at FROM orders ORDER BY created_at DESC LIMIT 10")
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await message.answer("📭 Нет заказов", reply_markup=get_admin_menu())
        return

    text = "<b>📦 Последние заказы:</b>\n\n"
    for order_id, name, username, city, total, created_at in orders:
        date = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m %H:%M")
        text += f"🆔 #{order_id} | 👤 {name} (@{username})\n📍 {city}\n💰 {total:.0f} BYN\n🕗 {date}\n\n"
    
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())

# ===== КАТАЛОГ И КОРЗИНА =====
@dp.message(F.text == "🛍 Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите категорию:", reply_markup=categories_keyboard())

@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    await callback.message.edit_text("Выберите категорию товаров:", reply_markup=categories_keyboard())
    await callback.answer()

# ===== КРИТИЧЕСКИ ИСПРАВЛЕНО: КНОПКИ РАБОТАЮТ НА МОБИЛЬНОМ КЛИЕНТЕ =====
@dp.callback_query(F.data.startswith("back_to_category_"))
async def back_to_category_products(callback: CallbackQuery):
    category = callback.data.replace("back_to_category_", "")
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products WHERE category = ? AND is_available = 1", (category,))
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        await callback.answer(f"В категории '{category}' нет товаров", show_alert=True)
        return
    
    # ИСПРАВЛЕНО: Используем безопасное редактирование сообщения
    try:
        await callback.message.edit_text(
            f"Категория: <b>{category}</b>\nВыберите товар:",
            reply_markup=products_keyboard(category),
            parse_mode="HTML"
        )
    except Exception as e:
        # Если редактирование невозможно (например, после отправки фото), отправляем новое сообщение
        await callback.message.answer(
            f"Категория: <b>{category}</b>\nВыберите товар:",
            reply_markup=products_keyboard(category),
            parse_mode="HTML"
        )
        try:
            await callback.message.delete()
        except:
            pass
    
    await callback.answer()

@dp.callback_query(F.data.startswith("category_"))
async def show_category_products(callback: CallbackQuery):
    if callback.data == "back_to_categories":
        await callback.message.edit_text("Выберите категорию товаров:", reply_markup=categories_keyboard())
        await callback.answer()
        return

    if callback.data.startswith("category_page_"):
        parts = callback.data.split("_")
        category = parts[2]
        page = int(parts[3])
        await callback.message.edit_text(
            f"Категория: <b>{category}</b>\nВыберите товар:",
            reply_markup=products_keyboard(category, page),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    category = callback.data.replace("category_", "")
    await callback.message.edit_text(
        f"Категория: <b>{category}</b>\nВыберите товар:",
        reply_markup=products_keyboard(category),
        parse_mode="HTML"
    )
    await callback.answer()

# ===== КРИТИЧЕСКИ ИСПРАВЛЕНО: КАРТОЧКА ТОВАРА ДЛЯ МОБИЛЬНОГО КЛИЕНТА =====
@dp.callback_query(F.data.startswith("product_"))
async def show_product_detail(callback: CallbackQuery):
    # Парсим данные: product_{id}_{category}
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("❌ Ошибка данных товара", show_alert=True)
        return
    
    product_id = int(parts[1])
    category = "_".join(parts[2:])  # На случай если в категории есть подчёркивания
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, description, price, photo_id FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    name, desc, price, photo = product

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM cart WHERE user_id = ? AND product_id = ?", (callback.from_user.id, product_id))
    in_cart = cursor.fetchone() is not None
    conn.close()

    text = f"<b>{name}</b>\n\n{desc}\n\n<b>Цена: {format_price(price)}</b>"
    
    # КРИТИЧЕСКИ ВАЖНО ДЛЯ МОБИЛЬНОГО: НЕ удаляем сообщение, а отправляем новое с фото
    if photo and photo.startswith("AgAC"):
        # Отправляем новое сообщение с фото и клавиатурой
        await callback.message.answer_photo(
            photo,
            caption=text,
            reply_markup=product_detail_keyboard(product_id, in_cart, category),
            parse_mode="HTML"
        )
        # Удаляем ТОЛЬКО если это безопасно (на ПК это работает, на мобильном — нет)
        # Поэтому НЕ удаляем старое сообщение — это вызывает проблемы на мобильном клиенте
        await callback.answer()
    else:
        # Для текстовых товаров редактируем сообщение
        try:
            await callback.message.edit_text(
                text,
                reply_markup=product_detail_keyboard(product_id, in_cart, category),
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                text,
                reply_markup=product_detail_keyboard(product_id, in_cart, category),
                parse_mode="HTML"
            )
            try:
                await callback.message.delete()
            except:
                pass
        await callback.answer()

@dp.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.replace("add_to_cart_", ""))
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1)", (callback.from_user.id, product_id))
    conn.commit()
    conn.close()
    
    # Получаем категорию из текущего сообщения (нужно для обновления клавиатуры)
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT category FROM products WHERE id = ?", (product_id,))
    category_row = cursor.fetchone()
    conn.close()
    
    category = category_row[0] if category_row else None
    
    # Обновляем клавиатуру с пометкой "В корзине"
    try:
        await callback.message.edit_reply_markup(
            reply_markup=product_detail_keyboard(product_id, in_cart=True, category=category)
        )
    except:
        pass
    
    await callback.answer("✅ Товар добавлен в корзину!", show_alert=True)

# ===== ИСПРАВЛЕНА КНОПКА "КОРЗИНА" В КАРТОЧКЕ ТОВАРА =====
@dp.callback_query(F.data == "view_cart")
async def view_cart_from_product(callback: CallbackQuery):
    await show_cart(callback)

@dp.message(F.text == "🛒 Корзина")
async def show_cart_message(message: types.Message):
    await show_cart(message)

async def show_cart(message_or_callback):
    if isinstance(message_or_callback, types.CallbackQuery):
        user_id = message_or_callback.from_user.id
        original_message = message_or_callback.message
    else:
        user_id = message_or_callback.from_user.id
        original_message = message_or_callback

    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.name, c.quantity, p.price 
        FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (user_id,))
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        text = "🛒 Корзина пуста"
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await original_message.edit_text(text, reply_markup=get_main_menu())
            except:
                await original_message.answer(text, reply_markup=get_main_menu())
            await message_or_callback.answer()
        else:
            await original_message.answer(text, reply_markup=get_main_menu())
        return
    
    total = sum(q * p for _, q, p in items)
    text = "<b>🛒 Корзина:</b>\n\n"
    for name, qty, price in items:
        text += f"• {name} × {qty} = {qty * price:.0f} BYN\n"
    text += f"\n<b>Итого: {total:.0f} BYN</b>"
    
    if isinstance(message_or_callback, types.CallbackQuery):
        try:
            await original_message.edit_text(text, parse_mode="HTML", reply_markup=cart_keyboard([(i, items[i][0], items[i][1], items[i][2]) for i in range(len(items))]))
        except:
            await original_message.answer(text, parse_mode="HTML", reply_markup=cart_keyboard([(i, items[i][0], items[i][1], items[i][2]) for i in range(len(items))]))
        await message_or_callback.answer()
    else:
        await original_message.answer(text, parse_mode="HTML", reply_markup=cart_keyboard([(i, items[i][0], items[i][1], items[i][2]) for i in range(len(items))]))

@dp.callback_query(F.data.startswith("remove_from_cart_"))
async def remove_from_cart(callback: CallbackQuery):
    item_id = int(callback.data.replace("remove_from_cart_", ""))
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE id = ? AND user_id = ?", (item_id, callback.from_user.id))
    conn.commit()
    conn.close()
    await show_cart(callback)

# ===== ИСПРАВЛЕНА КНОПКА "ОЧИСТИТЬ КОРЗИНУ" =====
@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="back_to_categories")
    kb.button(text="🛒 Корзина", callback_data="view_cart")
    kb.adjust(2)
    
    if deleted_rows > 0:
        message_text = "✅ Корзина успешно очищена!"
        alert_text = "Корзина очищена!"
    else:
        message_text = "🛒 Корзина уже пуста"
        alert_text = "Корзина пуста"
    
    try:
        await callback.message.edit_text(
            f"{message_text}\n\n🛒 Ваша корзина пуста.\nДобавьте товары из каталога!",
            reply_markup=kb.as_markup()
        )
    except:
        await callback.message.answer(
            f"{message_text}\n\n🛒 Ваша корзина пуста.\nДобавьте товары из каталога!",
            reply_markup=kb.as_markup()
        )
        try:
            await callback.message.delete()
        except:
            pass
    
    await callback.answer(alert_text, show_alert=True)

# ===== ИСПРАВЛЕНА КНОПКА "КОРЗИНА" ПРИ ОФОРМЛЕНИИ ЗАКАЗА =====
@dp.callback_query(F.data == "checkout")
async def checkout_start(callback: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM cart WHERE user_id = ?', (callback.from_user.id,))
    if cursor.fetchone()[0] == 0:
        conn.close()
        await callback.answer("Корзина пуста!")
        return
    conn.close()
    
    await state.update_data(checkout_message_id=callback.message.message_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Вернуться в корзину", callback_data="back_to_cart_from_checkout")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "📍 Укажите город доставки (любой город СНГ):",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderStates.waiting_for_city)
    await callback.answer()

@dp.callback_query(F.data == "back_to_cart_from_checkout")
async def back_to_cart_from_checkout(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cart(callback)

@dp.message(OrderStates.waiting_for_city)
async def get_city(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 2:
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Вернуться в корзину", callback_data="back_to_cart_from_checkout")
        kb.adjust(1)
        await message.answer("❌ Укажите корректный город:", reply_markup=kb.as_markup())
        return
    
    await state.update_data(city=message.text.strip())
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data="confirm_order_yes")
    kb.button(text="❌ Нет", callback_data="confirm_order_no")
    kb.adjust(2)
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.name, c.quantity, p.price 
        FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (message.from_user.id,))
    items = cursor.fetchall()
    total = sum(q * p for _, q, p in items)
    conn.close()
    
    await state.update_data(total=total, items=items)
    
    cart_text = "<b>🛒 Ваша корзина:</b>\n\n"
    for name, qty, price in items:
        cart_text += f"• {name} × {qty} = {qty * price:.0f} BYN\n"
    cart_text += f"\n<b>Итого: {total:.0f} BYN</b>"
    
    await message.answer(
        f"{cart_text}\n\n📍 Город доставки: {message.text.strip()}\n\n✅ Подтвердить заказ?",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await state.set_state(OrderStates.confirming_order)

@dp.callback_query(F.data == "confirm_order_yes")
async def confirm_order_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    city = data['city']
    total = data['total']
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (user_id, username, user_full_name, city, total_amount) VALUES (?, ?, ?, ?, ?)",
        (callback.from_user.id, callback.from_user.username, callback.from_user.full_name, city, total)
    )
    order_id = cursor.lastrowid
    
    cursor.execute('''
        SELECT c.id, p.id, p.name, c.quantity, p.price
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
    ''', (callback.from_user.id,))
    db_cart_items = cursor.fetchall()
    
    for _, product_id, product_name, quantity, price in db_cart_items:
        cursor.execute(
            "INSERT INTO order_items (order_id, product_id, product_name, quantity, price) VALUES (?, ?, ?, ?, ?)",
            (order_id, product_id, product_name, quantity, price)
        )
    
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (callback.from_user.id,))
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect('endorfina.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    conn.close()
    
    for admin in admins:
        try:
            await bot.send_message(
                admin[0],
                f"📦 <b>Новый заказ #{order_id}</b>\n👤 {callback.from_user.full_name} (@{callback.from_user.username})\n📍 {city}\n💰 {total:.0f} BYN",
                parse_mode="HTML"
            )
        except:
            pass
    
    await callback.message.edit_text(
        f"🎉 <b>Заказ #{order_id} оформлен!</b>\n\n"
        f"📍 Город: {city}\n"
        f"💰 К оплате: {total:.0f} BYN\n\n"
        "📱 Менеджер свяжется с вами для подтверждения",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    await callback.answer()
    await state.clear()

@dp.callback_query(F.data == "confirm_order_no")
async def confirm_order_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Заказ отменен",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# ===== ЗАПУСК =====
async def main():
    init_db()
    logger.info(f"Бот запущен. Код админки: {ADMIN_SECRET_CODE}")
    logger.info("✨ Приветственный GIF: локальный файл welcome.gif")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())