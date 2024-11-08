import os
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from dotenv import load_dotenv


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключение к базе данных
async def create_db_pool():
    return await asyncpg.create_pool(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

db_pool = None

# Обработка команды /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каталог", callback_data="catalog_1")]
    ])
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=keyboard)



# Отображение категорий
@dp.callback_query(lambda c: c.data.startswith("catalog_"))
async def show_categories(callback_query: types.CallbackQuery):
    page = int(callback_query.data.split("_")[1])
    offset = (page - 1) * 4

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name FROM botapp_category LIMIT $1 OFFSET $2", 4, offset)

    if not rows:
        await callback_query.message.answer("Категории не найдены.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=row["name"], callback_data=f"category_{row['id']}_1")] for row in rows
    ])
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"catalog_{page - 1}"))
    if len(rows) == 4:
        pagination_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"catalog_{page + 1}"))
    if pagination_buttons:
        keyboard.inline_keyboard.append(pagination_buttons)

    await callback_query.message.edit_text("Категории товаров:", reply_markup=keyboard)


# Отображение подкатегорий
@dp.callback_query(lambda c: c.data.startswith("category_"))
async def show_subcategories(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")


    if len(data) < 3 or not data[1].isdigit() or not data[2].isdigit():
        await callback_query.message.edit_text("Некорректные данные для подкатегории.")
        return

    category_id, page = int(data[1]), int(data[2])
    offset = (page - 1) * 4

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name FROM botapp_subcategory WHERE category_id = $1 LIMIT $2 OFFSET $3",
            category_id, 4, offset
        )

    if not rows:
        await callback_query.message.edit_text("В этой категории пока нет подкатегорий.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=row["name"], callback_data=f"subcategory_{row['id']}_1_{category_id}")] for row in rows
    ])
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"category_{category_id}_{page - 1}"))
    if len(rows) == 4:
        pagination_buttons.append(
            InlineKeyboardButton(text="Вперед ➡️", callback_data=f"category_{category_id}_{page + 1}"))
    if pagination_buttons:
        keyboard.inline_keyboard.append(pagination_buttons)


    keyboard.inline_keyboard.append(
        [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="catalog_1")]
    )


    if callback_query.message.text:
        await callback_query.message.edit_text("Подкатегории:", reply_markup=keyboard)
    else:
        await callback_query.message.answer("Подкатегории:", reply_markup=keyboard)

# Отображение товаров
@dp.callback_query(lambda c: c.data.startswith("subcategory_"))
async def show_products(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    subcategory_id, category_id = int(data[1]), int(data[2])
    await show_product(callback_query, subcategory_id, category_id, product_index=1)


# Отображение конкретного товара
async def show_product(callback_query: types.CallbackQuery, subcategory_id: int, category_id: int, product_index: int):
    offset = product_index - 1

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, description, price, photo FROM botapp_product WHERE subcategory_id = $1 OFFSET $2 LIMIT 1",
            subcategory_id, offset
        )

    if not row:
        await callback_query.message.edit_text("Товар не найден.")
        return


    text = f"<b>{row['name']}</b>\n{row['description']}\nЦена: {row['price']} руб.\nТовар {product_index}"
    photo_filename = row['photo']
    file_path = os.path.join(photo_filename)


    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к подкатегориям", callback_data=f"category_{category_id}_1")],
        [InlineKeyboardButton(text="🛒 Добавить в корзину", callback_data=f"add_to_cart_{row['id']}")],
        [InlineKeyboardButton(text="💸 Купить", callback_data="buy_product")],
        [
            InlineKeyboardButton(text="⬅️ Пред.",
                                 callback_data=f"product_{subcategory_id}_{category_id}_{product_index - 1}"),
            InlineKeyboardButton(text="След. ➡️",
                                 callback_data=f"product_{subcategory_id}_{category_id}_{product_index + 1}")
        ]
    ])


    if os.path.exists(file_path):
        photo = FSInputFile(file_path)
        await bot.edit_message_media(
            media=types.InputMediaPhoto(media=photo, caption=text, parse_mode="HTML"),
            chat_id=callback_query.from_user.id,
            message_id=callback_query.message.message_id,
            reply_markup=keyboard
        )
    else:
        await callback_query.message.edit_caption(
            caption=f"Фото для {row['name']} не найдено.\n\n{text}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

# Обработка кнопок "Пред." и "След."
@dp.callback_query(lambda c: c.data.startswith("product_"))
async def navigate_products(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    subcategory_id, category_id, product_index = int(data[1]), int(data[2]), int(data[3])

    async with db_pool.acquire() as conn:
        product_count = await conn.fetchval("SELECT COUNT(*) FROM botapp_product WHERE subcategory_id = $1", subcategory_id)

    if product_index < 1:
        await callback_query.answer("Это первый товар.")
    elif product_index > product_count:
        await callback_query.answer("Это последний товар.")
    else:
        await show_product(callback_query, subcategory_id, category_id, product_index)



async def main():
    global db_pool
    db_pool = await create_db_pool()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
