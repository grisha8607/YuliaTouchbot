import os
import sys
import asyncio
import random
import sqlite3
import calendar
from datetime import date, datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8359132215:AAFYDj_4UBiy1I53-NF1acT8JZsGSysJG2I"
ADMIN_IDS = {5931871517, 1071504095}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
IMAGES_FOLDER = os.path.join(BASE_DIR, "images")
QR_FOLDER = os.path.join(BASE_DIR, "qr")
os.makedirs(IMAGES_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

TIME_SLOTS = [f"{h}:00" for h in range(10, 21)]

calendar.setfirstweekday(calendar.MONDAY)
MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# ================== БОТ ==================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ================== FSM ==================
class Booking(StatesGroup):
    choosing_date = State()
    choosing_time = State()


# ================== FSM для редактирования контента ==================
class EditContent(StatesGroup):
    choosing_section = State()
    entering_text = State()


# ================== БАЗА ==================
def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            time TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS closed_slots (
            date TEXT,
            time TEXT,
            reason TEXT DEFAULT NULL,
            PRIMARY KEY (date, time)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS closed_dates (
            date TEXT PRIMARY KEY,
            reason TEXT DEFAULT NULL
        )
    """)
    # ✅ Таблица для хранения редактируемого контента
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS content (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()

    # Заполняем дефолтный контент, если таблица пустая
    defaults = {
        "welcome": (
            "🪷 *Добро пожаловать в YuliaTouch*\n\n"
            "Профессиональный расслабляющий и лечебный массаж\n"
            "Только натуральные масла и индивидуальный подход\n\n"
            "Расслабьтесь и доверьтесь рукам мастера 💆‍♀️\n\n"
            "Выберите, что вас интересует 👇"
        ),
        "services": (
            "🪷 *Основные виды массажа*\n\n"
            "💆‍♀️ Классический расслабляющий — 60/90 мин\n"
            "🌀 Лимфодренажный — вывод токсинов, отёки\n"
            "🔥 Антицеллюлитный + баночный — коррекция фигуры\n"
            "👐 Спортивный восстановительный — после тренировок\n"
            "🌿 Аромамассаж — с эфирными маслами\n"
            "🪨 Стоун-массаж (горячие камни) — глубокое расслабление\n\n"
            "Длительность и цена подбираются индивидуально 💫"
        ),
        "oils": (
            "🧴 *Натуральные масла и уход*\n\n"
            "Использую только органические масла холодного отжима:\n"
            "• Аргановое\n• Жожоба\n• Кокосовое\n• Миндальное\n• Ши\n• Эфирные масла\n\n"
            "После сеанса кожа бархатная, а тело наполнено энергией ✨"
        ),
        "contacts": (
            "📍 *YuliaTouch — массаж в Москве*\n\n"
            "🕰 Приём только по предварительной записи\n"
            "📲 Telegram / WhatsApp\n"
            "🚇 Рядом с метро (уточняйте адрес при записи)\n\n"
            "Пишите — подберу для вас идеальное время и программу 💕"
        ),
        "payment": (
            "💳 *Оплата сеанса*\n\n"
            "Отсканируйте QR-код\n"
            "После оплаты напишите «оплачено» и я подтвержу запись\n\n"
            "Сумму уточняйте при бронировании"
        ),
    }
    for key, value in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO content (key, value) VALUES (?, ?)",
            (key, value)
        )
    conn.commit()
    conn.close()


# ================== ПОЛУЧИТЬ КОНТЕНТ ==================
def get_content(key: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM content WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""


def set_content(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO content (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()


# ================== УТИЛИТЫ ==================
def random_image():
    imgs = [f for f in os.listdir(IMAGES_FOLDER) if f.lower().endswith(("jpg", "png", "jpeg"))]
    return os.path.join(IMAGES_FOLDER, random.choice(imgs)) if imgs else None


def generate_qr():
    import qrcode
    code = random.randint(100000, 999999)
    path = os.path.join(QR_FOLDER, f"pay_{code}.png")
    qrcode.make(f"https://pay.example/{code}").save(path)
    return path


def calendar_keyboard(year, month, for_admin=False):
    kb = []
    cal = calendar.monthcalendar(year, month)
    kb.append([InlineKeyboardButton(text=f"{MONTHS_RU[month]} {year}", callback_data="ignore")])
    kb.append([InlineKeyboardButton(text=d, callback_data="ignore") for d in WEEKDAYS_RU])

    conn = get_connection()
    cursor = conn.cursor()

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
                continue

            day_date = date(year, month, day)
            if day_date < date.today() or day_date > date.today() + timedelta(days=90):
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
                continue

            day_str = f"{year}-{month:02d}-{day:02d}"

            cursor.execute("SELECT 1 FROM closed_dates WHERE date=?", (day_str,))
            is_closed = cursor.fetchone() is not None

            cursor.execute(
                "SELECT COUNT(*) FROM appointments WHERE date=? AND status IN ('pending', 'confirmed')",
                (day_str,)
            )
            has_appointments = cursor.fetchone()[0] > 0

            if is_closed:
                text = f"⛔ {day}"
            elif has_appointments:
                text = f"🔥 {day}" if for_admin else f"{day} 🔥"
            else:
                text = str(day)

            row.append(InlineKeyboardButton(text=text, callback_data=f"date:{day_str}"))
        kb.append(row)

    conn.close()

    kb.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"prev:{year}:{month}"),
        InlineKeyboardButton(text="➡️", callback_data=f"next:{year}:{month}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def time_slots_keyboard(chosen_date):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM closed_dates WHERE date=?", (chosen_date,))
    day_closed = cursor.fetchone() is not None

    if day_closed:
        conn.close()
        kb = [
            [InlineKeyboardButton(text="⛔ День полностью закрыт", callback_data="ignore")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh:{chosen_date}")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=kb)

    cursor.execute(
        "SELECT time FROM appointments WHERE date=? AND status IN ('pending', 'confirmed')",
        (chosen_date,)
    )
    booked = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT time FROM closed_slots WHERE date=?", (chosen_date,))
    closed = {row[0] for row in cursor.fetchall()}

    conn.close()

    kb = []
    for t in TIME_SLOTS:
        if t in booked:
            kb.append([InlineKeyboardButton(text=f"❌ {t} (забронировано)", callback_data="ignore")])
        elif t in closed:
            kb.append([InlineKeyboardButton(text=f"🚫 {t} (закрыто)", callback_data="ignore")])
        else:
            kb.append([InlineKeyboardButton(text=t, callback_data=f"time:{t}")])

    kb.append([InlineKeyboardButton(text="🔄 Обновить доступное время", callback_data=f"refresh:{chosen_date}")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def status_label(status: str) -> str:
    labels = {
        "pending": "⏳ Ожидает подтверждения",
        "confirmed": "✅ Подтверждена",
    }
    return labels.get(status, status)


# ================== КНОПКИ ==================
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🪷 Услуги массажа"), KeyboardButton(text="🧴 Масла и уход")],
        [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="📍 Контакты")],
        [KeyboardButton(text="🫶 Записаться"), KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="❌ Отменить запись")]
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🪷 Услуги массажа"), KeyboardButton(text="🧴 Масла и уход")],
        [KeyboardButton(text="💳 Оплата"), KeyboardButton(text="📍 Контакты")],
        [KeyboardButton(text="🫶 Записаться"), KeyboardButton(text="📋 Мои записи")],
        [KeyboardButton(text="❌ Отменить запись")],
        [KeyboardButton(text="📅 Админ: Календарь записей"), KeyboardButton(text="✏️ Админ: Редактор контента")]
    ],
    resize_keyboard=True
)

# Названия секций для удобства
SECTION_LABELS = {
    "welcome": "👋 Приветствие (/start)",
    "services": "🪷 Услуги массажа",
    "oils": "🧴 Масла и уход",
    "contacts": "📍 Контакты",
    "payment": "💳 Оплата (текст под QR)",
}


# ================== ХЕНДЛЕРЫ ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = admin_kb if message.from_user.id in ADMIN_IDS else user_kb
    await message.answer(
        get_content("welcome"),
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.message(lambda m: m.text == "🪷 Услуги массажа")
async def services(message: types.Message):
    text = get_content("services")
    img = random_image()
    if img:
        await message.answer_photo(FSInputFile(img), caption=text, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


@dp.message(lambda m: m.text == "🧴 Масла и уход")
async def oils(message: types.Message):
    await message.answer(get_content("oils"), parse_mode="Markdown")


@dp.message(lambda m: m.text == "📍 Контакты")
async def contacts(message: types.Message):
    await message.answer(get_content("contacts"), parse_mode="Markdown")


@dp.message(lambda m: m.text == "💳 Оплата")
async def payment(message: types.Message):
    qr = generate_qr()
    await message.answer_photo(
        FSInputFile(qr),
        caption=get_content("payment"),
        parse_mode="Markdown"
    )


@dp.message(lambda m: m.text == "📋 Мои записи")
async def my_appointments(message: types.Message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, date, time, status FROM appointments "
        "WHERE user_id=? AND status IN ('pending', 'confirmed') "
        "ORDER BY date ASC, time ASC",
        (message.from_user.id,)
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await message.answer("📋 У вас пока нет активных записей.\n\nЖелаете записаться? Нажмите «🫶 Записаться» 😊")
        return
    lines = ["📋 *Ваши записи:*\n"]
    kb_buttons = []
    for idx, (appt_id, date_str, time_str, status) in enumerate(rows, start=1):
        lines.append(f"{idx}. 📅 {date_str} ⏰ {time_str} — {status_label(status)}")
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"❌ Отменить запись #{idx}",
                callback_data=f"cancel:{appt_id}"
            )
        ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@dp.message(lambda m: m.text == "🫶 Записаться")
async def booking_start(message: types.Message, state: FSMContext):
    today = date.today()
    await message.answer(
        "📅 Выберите дату (следующие 3 месяца):",
        reply_markup=calendar_keyboard(today.year, today.month, for_admin=False)
    )
    await state.set_state(Booking.choosing_date)


@dp.message(lambda m: m.text == "📅 Админ: Календарь записей")
async def admin_calendar_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта функция доступна только администратору.")
        return
    today = date.today()
    await message.answer(
        "📅 Календарь записей (выберите дату):",
        reply_markup=calendar_keyboard(today.year, today.month, for_admin=True)
    )


# ================== ✏️ РЕДАКТОР КОНТЕНТА ==================

def edit_menu_keyboard():
    """Инлайн-клавиатура с выбором раздела для редактирования."""
    buttons = []
    for key, label in SECTION_LABELS.items():
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"edit_section:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(lambda m: m.text == "✏️ Админ: Редактор контента")
async def admin_editor_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта функция доступна только администратору.")
        return
    await state.clear()
    await message.answer(
        "✏️ *Редактор контента*\n\n"
        "Выберите раздел, который хотите изменить:\n\n"
        "⚠️ Поддерживается Markdown-разметка:\n"
        "`*жирный*`  `_курсив_`  `` `код` ``",
        parse_mode="Markdown",
        reply_markup=edit_menu_keyboard()
    )
    await state.set_state(EditContent.choosing_section)


@dp.callback_query(lambda c: c.data.startswith("edit_section:"), EditContent.choosing_section)
async def admin_section_chosen(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    key = callback.data.split(":", 1)[1]
    label = SECTION_LABELS.get(key, key)
    current_text = get_content(key)

    await state.update_data(editing_key=key)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel")]
    ])

    await callback.message.answer(
        f"✏️ Редактирование: *{label}*\n\n"
        f"📄 Текущий текст:\n\n{current_text}\n\n"
        "─────────────────────\n"
        "Отправьте новый текст для этого раздела.\n"
        "Поддерживается Markdown (`*жирный*`, `_курсив_` и т.д.)",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await state.set_state(EditContent.entering_text)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "edit_cancel")
async def admin_edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "❌ Редактирование отменено.",
        reply_markup=edit_menu_keyboard()
    )
    await callback.answer()


@dp.message(EditContent.entering_text)
async def admin_save_content(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    key = data.get("editing_key")

    if not key:
        await state.clear()
        return

    new_text = message.text.strip()
    label = SECTION_LABELS.get(key, key)

    # Сохраняем
    set_content(key, new_text)

    # Показываем результат с предпросмотром
    preview_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать ещё", callback_data=f"edit_section:{key}")],
        [InlineKeyboardButton(text="📋 К списку разделов", callback_data="edit_back_to_menu")]
    ])

    await message.answer(
        f"✅ Раздел *{label}* успешно обновлён!\n\n"
        f"📄 *Предпросмотр:*\n\n{new_text}",
        parse_mode="Markdown",
        reply_markup=preview_kb
    )
    await state.clear()


@dp.callback_query(lambda c: c.data == "edit_back_to_menu")
async def admin_back_to_edit_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(EditContent.choosing_section)
    await callback.message.answer(
        "✏️ *Редактор контента* — выберите раздел:",
        parse_mode="Markdown",
        reply_markup=edit_menu_keyboard()
    )
    await callback.answer()


# ================== КАЛЕНДАРЬ НАВИГАЦИЯ ==================
@dp.callback_query(lambda c: c.data.startswith(("prev", "next")))
async def change_month(callback: types.CallbackQuery):
    _, y, m = callback.data.split(":")
    y, m = int(y), int(m)
    if callback.data.startswith("prev"):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    else:
        m += 1
        if m == 13:
            m = 1
            y += 1
    for_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.edit_reply_markup(reply_markup=calendar_keyboard(y, m, for_admin=for_admin))
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("date:"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    chosen_date = callback.data.split(":")[1]

    if callback.from_user.id in ADMIN_IDS:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT reason FROM closed_dates WHERE date=?", (chosen_date,))
        day_closed = cursor.fetchone()

        cursor.execute("""
            SELECT time, user_id, status
            FROM appointments
            WHERE date = ? AND status IN ('pending', 'confirmed')
            ORDER BY time
        """, (chosen_date,))
        rows = cursor.fetchall()

        lines = [f"📅 Записи на {chosen_date}:"]
        if rows:
            for time, user_id, status in rows:
                lines.append(f"⏰ {time} — пользователь {user_id} — {status_label(status)}")
        else:
            lines.append("Нет активных записей клиентов.")

        if day_closed:
            lines.append(f"\nДень полностью закрыт ⛔ (причина: {day_closed[0] or 'не указана'})")
            kb_day = [[InlineKeyboardButton(text="Открыть весь день", callback_data=f"open_day:{chosen_date}")]]
        else:
            lines.append("\nДень открыт")
            kb_day = [[InlineKeyboardButton(text="Закрыть весь день", callback_data=f"close_day:{chosen_date}")]]

        lines.append("\nУправление отдельными слотами:")

        cursor.execute("SELECT time FROM closed_slots WHERE date=?", (chosen_date,))
        closed = {row[0] for row in cursor.fetchall()}

        kb_slots = []
        for t in TIME_SLOTS:
            if t in closed:
                btn_text = f"Открыть {t}"
                cb_data = f"open_slot:{chosen_date}:{t}"
            else:
                btn_text = f"Закрыть {t}"
                cb_data = f"close_slot:{chosen_date}:{t}"
            kb_slots.append([InlineKeyboardButton(text=btn_text, callback_data=cb_data)])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_day + kb_slots)

        await callback.message.answer("\n".join(lines), reply_markup=kb)

        conn.close()
        await callback.answer()
        return

    # Обычный пользователь
    await state.update_data(date=chosen_date)
    kb = time_slots_keyboard(chosen_date)

    text = (
        f"⏰ Доступное время на {chosen_date}:\n\n"
        "• Занятые слоты — ❌\n"
        "• Закрытые админом — 🚫\n"
        "• Закрытые дни отмечены ⛔ в календаре\n"
        "• Если список выглядит устаревшим — нажмите «Обновить доступное время»"
    )

    if not any(btn.callback_data.startswith("time:") for row in kb.inline_keyboard for btn in row if len(row) > 0):
        await callback.message.answer("На выбранную дату пока нет свободных слотов 😔")
    else:
        await callback.message.answer(text, reply_markup=kb)

    await state.set_state(Booking.choosing_time)
    await callback.answer()


# ================== ЗАКРЫТИЕ/ОТКРЫТИЕ ДНЯ ==================
@dp.callback_query(lambda c: c.data.startswith("close_day:"))
async def close_day(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступно только администратору", show_alert=True)
        return
    _, date_str = callback.data.split(":", 1)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO closed_dates (date, reason) VALUES (?, ?)", (date_str, "закрыто админом"))
    conn.commit()
    conn.close()
    await callback.answer(f"День {date_str} полностью закрыт", show_alert=True)
    await callback.message.answer(f"День {date_str} закрыт для записи ⛔")


@dp.callback_query(lambda c: c.data.startswith("open_day:"))
async def open_day(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступно только администратору", show_alert=True)
        return
    _, date_str = callback.data.split(":", 1)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM closed_dates WHERE date=?", (date_str,))
    conn.commit()
    conn.close()
    await callback.answer(f"День {date_str} открыт", show_alert=True)
    await callback.message.answer(f"День {date_str} открыт для записи.")


# ================== ЗАКРЫТИЕ/ОТКРЫТИЕ СЛОТА ==================
@dp.callback_query(lambda c: c.data.startswith("close_slot:"))
async def close_slot(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступно только администратору", show_alert=True)
        return
    _, date_str, time_str = callback.data.split(":", 2)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO closed_slots (date, time) VALUES (?, ?)", (date_str, time_str))
    conn.commit()
    conn.close()
    await callback.answer(f"Слот {time_str} на {date_str} закрыт", show_alert=True)
    await callback.message.answer(f"Слот {time_str} закрыт.")


@dp.callback_query(lambda c: c.data.startswith("open_slot:"))
async def open_slot(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступно только администратору", show_alert=True)
        return
    _, date_str, time_str = callback.data.split(":", 2)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM closed_slots WHERE date=? AND time=?", (date_str, time_str))
    conn.commit()
    conn.close()
    await callback.answer(f"Слот {time_str} открыт", show_alert=True)
    await callback.message.answer(f"Слот {time_str} открыт.")


# ================== ОБНОВЛЕНИЕ ВРЕМЕНИ ==================
@dp.callback_query(lambda c: c.data.startswith("refresh:"))
async def refresh_times(callback: types.CallbackQuery, state: FSMContext):
    try:
        chosen_date = callback.data.split(":", 1)[1]
        await state.update_data(date=chosen_date)
        kb = time_slots_keyboard(chosen_date)
        await callback.message.answer(
            f"⏰ Доступное время на {chosen_date} (обновлено):\n\n"
            "• Занятые слоты — ❌\n"
            "• Закрытые админом — 🚫\n"
            "• Нажмите «Обновить», если список кажется старым",
            reply_markup=kb
        )
        await callback.answer("Список обновлён ✓")
    except Exception as e:
        print(f"[ERROR refresh] {e}", file=sys.stderr)
        await callback.answer("Не удалось обновить список", show_alert=True)


@dp.callback_query(lambda c: c.data == "ignore")
async def ignore_press(callback: types.CallbackQuery):
    await callback.answer()


# ================== ВЫБОР ВРЕМЕНИ ==================
@dp.callback_query(lambda c: c.data.startswith("time:"), Booking.choosing_time)
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
    time = callback.data.split(":")[1]
    data = await state.get_data()
    chosen_date = data.get("date")
    if not chosen_date:
        await callback.answer("Сессия истекла", show_alert=True)
        await state.clear()
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM appointments WHERE date=? AND time=? AND status IN ('pending', 'confirmed')",
        (chosen_date, time)
    )
    if cursor.fetchone():
        conn.close()
        await callback.answer("Это время уже занято", show_alert=True)
        kb = time_slots_keyboard(chosen_date)
        await callback.message.answer(f"⏰ Доступное время на {chosen_date} (обновлено):", reply_markup=kb)
        return

    cursor.execute(
        "INSERT INTO appointments (user_id, date, time) VALUES (?, ?, ?)",
        (callback.from_user.id, chosen_date, time)
    )
    appointment_id = cursor.lastrowid
    conn.commit()
    conn.close()

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{appointment_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel:{appointment_id}")
        ]
    ])

    await callback.message.edit_text(
        f"📅 {chosen_date} ⏰ {time}\n\nПодтвердите запись:",
        reply_markup=confirm_kb
    )

    await bot.send_message(
        list(ADMIN_IDS)[0],
        f"🆕 Новая запись (ожидает)\n📅 {chosen_date} ⏰ {time}\n👤 {callback.from_user.first_name or callback.from_user.id}"
    )

    await state.clear()
    await callback.answer()


# ================== ПОДТВЕРЖДЕНИЕ / ОТМЕНА ==================
@dp.callback_query(lambda c: c.data.startswith("confirm:"))
async def confirm_appointment(callback: types.CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointments SET status='confirmed' WHERE id=?", (appointment_id,))
    conn.commit()
    cursor.execute("SELECT user_id, date, time FROM appointments WHERE id=?", (appointment_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        user_id, date_str, time_str = row
        await bot.send_message(user_id, f"✅ Ваша запись на {date_str} ⏰ {time_str} подтверждена.")
        await bot.send_message(list(ADMIN_IDS)[0], f"✅ Запись подтверждена: {date_str} ⏰ {time_str}")
    await callback.message.edit_text("✅ Запись подтверждена.")
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("cancel:"))
async def cancel_appointment(callback: types.CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, date, time FROM appointments WHERE id=?", (appointment_id,))
    row = cursor.fetchone()
    if not row:
        await callback.answer("Запись уже удалена.", show_alert=True)
        conn.close()
        return
    user_id, date_str, time_str = row
    cursor.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appointment_id,))
    conn.commit()
    conn.close()
    await bot.send_message(user_id, f"❌ Ваша запись на {date_str} ⏰ {time_str} отменена.")
    await bot.send_message(list(ADMIN_IDS)[0], f"❌ Запись отменена: {date_str} ⏰ {time_str}")
    await callback.message.edit_text("❌ Запись отменена.")
    await callback.answer()


@dp.message(lambda m: m.text == "❌ Отменить запись")
async def cancel_user_booking(message: types.Message):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, date, time, status FROM appointments "
        "WHERE user_id=? AND status IN ('pending','confirmed') ORDER BY id DESC LIMIT 1",
        (message.from_user.id,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        await message.answer("❌ У вас нет активных записей для отмены.")
        return
    appointment_id, date_str, time_str, status = row
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Подтвердить отмену", callback_data=f"cancel:{appointment_id}")]
    ])
    await message.answer(f"Вы выбрали запись на {date_str} ⏰ {time_str}\n\nПодтвердите отмену:", reply_markup=kb)


# ================== ЗАПУСК ==================
async def main():
    init_db()
    print("YuliaTouch запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())