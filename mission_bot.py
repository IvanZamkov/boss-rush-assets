# mission_bot_with_validation.py
import telebot
from telebot.types import (
    InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton
)
import random
import uuid
import os
import traceback
import sqlite3
import json

# Настройки
BOT_TOKEN = "8518491353:AAHOdT0RY8Dlt7kkpXR7speVtiSfTZmVxYM" # <-- замени на свой токен
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOSSES_FILE = os.path.join(BASE_DIR, "bosses.txt")
CHARS_FILE = os.path.join(BASE_DIR, "characters.txt")
DB_FILE = os.path.join(BASE_DIR, "user_lists.db")

# Миниатюры
THUMBS = {
    1: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_1.jpg",
    2: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_2.jpg",
    3: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_3.jpg",
    4: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_4.jpg",
}

# DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_lists (
            user_id INTEGER NOT NULL,
            list_type TEXT NOT NULL, -- 'characters' or 'bosses'
            items TEXT NOT NULL,     -- JSON array
            PRIMARY KEY (user_id, list_type)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Файловые операции
def load_file_list(path):
    if not os.path.exists(path):
        open(path, "a", encoding="utf-8").close()
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_file_list(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(f"{item}\n")

# DB (user lists)
def get_db_list(user_id: int, list_type: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT items FROM user_lists WHERE user_id=? AND list_type=?", (user_id, list_type))
    row = cur.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return []
    return None  #=> кастомного списка нет

def save_db_list(user_id: int, list_type: str, items: list):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    js = json.dumps(items, ensure_ascii=False)
    cur.execute("""
        INSERT INTO user_lists (user_id, list_type, items)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, list_type) DO UPDATE SET items=excluded.items
    """, (user_id, list_type, js))
    conn.commit()
    conn.close()

def delete_db_list(user_id: int, list_type: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_lists WHERE user_id=? AND list_type=?", (user_id, list_type))
    conn.commit()
    conn.close()

# Вспом. функции
def normalize_type(token: str):
    token = (token or "").lower().strip()
    if token in ("персонаж", "персонажи", "characters", "character", "chars", "char"):
        return "characters"
    if token in ("босс", "боссы", "boss", "bosses"):
        return "bosses"
    return None

# Получить список для пользователя: кастомный (если есть) или файл по умолчанию
def get_list_for_user(user_id: int, list_type: str):
    db_list = get_db_list(user_id, list_type)
    if db_list is not None:
        return db_list, True
    if list_type == "characters":
        return load_file_list(CHARS_FILE), False
    else:
        return load_file_list(BOSSES_FILE), False

# получаем "главные" (файловые) списки в нормализованном виде для валидации
def load_main_lists():
    chars = load_file_list(CHARS_FILE)
    bosses = load_file_list(BOSSES_FILE)
    # словари: lower() -> canonical (оригинальная запись)
    chars_map = {c.lower(): c for c in chars}
    bosses_map = {b.lower(): b for b in bosses}
    return chars_map, bosses_map

# проверка одного имени на соответствие списку типа
def validate_name_against_main(name: str, target_type: str):
    chars_map, bosses_map = load_main_lists()
    name_l = (name or "").strip().lower()
    errors = []
    found_in_chars = name_l in chars_map
    found_in_bosses = name_l in bosses_map

    if not found_in_chars and not found_in_bosses:
        errors.append(f"Имя '{name}' не найдено ни в главном списке персонажей, ни в главном списке боссов.")
        return False, errors

    if target_type == "characters" and not found_in_chars:
        # имя есть, но в босcах
        errors.append(f"Имя '{name}' присутствует в списке боссов, а указано для списка персонажей.")
        return False, errors

    if target_type == "bosses" and not found_in_bosses:
        errors.append(f"Имя '{name}' присутствует в списке персонажей, а указано для списка боссов.")
        return False, errors

    return True, []

# нормализовать имена — взять "каноническую" запись из файлов (с правильным регистром)
def canonicalize_name_from_main(name: str, target_type: str):
    chars_map, bosses_map = load_main_lists()
    name_l = (name or "").strip().lower()
    if target_type == "characters":
        return chars_map.get(name_l, name.strip())
    else:
        return bosses_map.get(name_l, name.strip())

# парсинг аргументов для простых команд (тип и остальное)
def parse_args_after_command(message_text: str):
    parts = message_text.split(maxsplit=2)
    if len(parts) >= 2:
        return parts[1], (parts[2] if len(parts) >= 3 else "")
    return None, ""

# Inline генерация сообщения (использует список конкретного пользователя)
def make_message_for_user(user_id: int, num_chars: int) -> str:
    bosses, _ = get_list_for_user(user_id, "bosses")
    characters, _ = get_list_for_user(user_id, "characters")

    boss = random.choice(bosses) if bosses else "boss_error"
    if num_chars <= 1:
        char = random.choice(characters) if characters else "char_error"
        return f"⚔ Победи босса {boss} персонажем {char}"
    else:
        if len(characters) >= num_chars:
            chosen = random.sample(characters, num_chars)
        else:
            chosen = [random.choice(characters) if characters else "char_error" for _ in range(num_chars)]
        names = ", ".join(chosen)
        return f"⚔ Победи босса {boss} отрядом: {names}"

# Inline handler
@bot.inline_handler(lambda query: True)
def inline_query_handler(inline_query):
    try:
        results = []
        user_id = inline_query.from_user.id if inline_query.from_user else None

        for n in range(1, 5):
            try:
                text = make_message_for_user(user_id, n)
                content = InputTextMessageContent(text)
                title = "Одиночное испытание" if n == 1 else f"Отряд из {n} персонажей"
                kwargs = {
                    "id": str(uuid.uuid4()),
                    "title": title,
                    "input_message_content": content,
                    "description": ""
                }
                thumb = THUMBS.get(n)
                if thumb:
                    if thumb.startswith("https://"):
                        kwargs["thumbnail_url"] = thumb
                    else:
                        print(f"[WARN] Миниатюра для {n} не использована (не https): {thumb}")
                
                random_links = [
                    ("👉 Узнай, кто ты из порно актеров", "https://t.me/HowYourPolite/26"),
                    ("👴 Узнай, какой ты Путин сегодня", "https://t.me/HowYourPolite/26"),
                    ("🎧 Подкаст стендаперов", "https://t.me/RP_Govno_canal"),
                    ("🎁 Получи подарок гифтом", "https://t.me/HowYourPolite/28")
                    ]
                label_rand, url_rand = random.choice(random_links)
                markup = InlineKeyboardMarkup()
                btn_random = InlineKeyboardButton(label_rand, url=url_rand)
                btn_result = InlineKeyboardButton("Узнать свой результат", switch_inline_query_current_chat="")
                markup.row(btn_random)                
                markup.row(btn_result)
                kwargs["reply_markup"] = markup

                result = InlineQueryResultArticle(**kwargs)
                results.append(result)

            except Exception as e_item:
                print(f"[ERROR] Ошибка при создании результата для {n}: {e_item}")
                traceback.print_exc()

        if not results:
            results = [InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="(Ошибка) Генерация недоступна",
                input_message_content=InputTextMessageContent("⚠️ Сейчас не получилось сгенерировать результат. Попробуйте позже."),
                description="Проблема на стороне бота"
            )]

        bot.answer_inline_query(
            inline_query.id,
            results,
            cache_time=0,
            switch_pm_text="⚙️Открыть настройки",
            switch_pm_parameter="from_inline"
        )

        print(f"[INFO] inline_query handled, returned {len(results)} items for qid={inline_query.id}")

    except Exception as e:
        print("[CRITICAL] Ошибка inline handler'а:", e)
        traceback.print_exc()
        try:
            bot.answer_inline_query(inline_query.id, [
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="Ошибка",
                    input_message_content=InputTextMessageContent("⚠️ Бот временно недоступен."),
                    description="Попробуйте позже"
                )
            ], cache_time=0)
        except Exception:
            pass

# Команды управления: start / add / delete / edit / reset / show
@bot.message_handler(commands=['start'])
def cmd_start(message):
    args = message.text.split(maxsplit=1)
    param = None
    if len(args) > 1:
        param = args[1].strip()
    if param:
        bot.reply_to(message, f"⚙️Используйте команды управления списками:\n/add, /edit, /delete, /reset \n📜Просмотр списков: /show")

@bot.message_handler(commands=['add'])
def cmd_add(message):
    # /add {персонаж/босс} имя
    user_id = message.from_user.id
    text = message.text or ""
    typ_token, name = parse_args_after_command(text)
    list_type = normalize_type(typ_token or "")
    if not list_type or not name:
        bot.reply_to(message, "⚙️Использование: /add {персонаж|босс} имя\nПример: /add персонаж Ке Цин")
        return

    name = name.strip()
    # 1) проверяем имя по главным спискам
    ok, errs = validate_name_against_main(name, list_type)
    if not ok:
        bot.reply_to(message, "❗Ошибки при валидации:\n" + "\n".join(errs))
        return

    # 2) формируем текущий список пользователя (создаём кастомный, если не было)
    cur_list, is_custom = get_list_for_user(user_id, list_type)
    if not is_custom:
        # создаём кастомную копию из файла (чтобы изменения не трогали глобальный файл)
        save_db_list(user_id, list_type, cur_list)
        is_custom = True

    # 3) проверяем дубликат в текущем списке (ignorе case)
    name_l = name.lower()
    if any(x.lower() == name_l for x in cur_list):
        bot.reply_to(message, f"✖️ Имя {name} уже присутствует в вашем текущем списке. Добавление отменено.")
        return

    # 4) сохраняем каноническое имя (как в главном файле)
    canonical = canonicalize_name_from_main(name, list_type)
    cur_list.append(canonical)
    save_db_list(user_id, list_type, cur_list)
    bot.reply_to(message, f"✔️ Добавлено в ваш кастомный список ({'персонажи' if list_type=='characters' else 'боссы'}): {canonical}")

@bot.message_handler(commands=['delete'])
def cmd_delete(message):
    # /delete {персонаж/босс} имя
    user_id = message.from_user.id
    text = message.text or ""
    typ_token, name = parse_args_after_command(text)
    list_type = normalize_type(typ_token or "")
    if not list_type or not name:
        bot.reply_to(message, "⚙️Использование: /delete {персонаж|босс} имя\nПример: /delete босс Ужас Бури")
        return

    name = name.strip()
    # создаём кастомную копию, если её нет (чтобы не трогать глобальный файл)
    cur_list, is_custom = get_list_for_user(user_id, list_type)
    if not is_custom:
        save_db_list(user_id, list_type, cur_list)
        cur_list, is_custom = get_list_for_user(user_id, list_type)

    # проверяем, есть ли такое имя в текущем списке (case-insensitive)
    name_l = name.lower()
    matches = [x for x in cur_list if x.lower() == name_l]
    if not matches:
        bot.reply_to(message, f"✖️ Имя {name} не найдено в вашем текущем списке. Удаление отменено.")
        return

    # удаляем все вхождения, если они есть
    cur_list = [x for x in cur_list if x.lower() != name_l]
    save_db_list(user_id, list_type, cur_list)
    bot.reply_to(message, f"✔️ Удалено: {matches[0]}")

@bot.message_handler(commands=['edit'])
def cmd_edit(message):
    # /edit {персонажи/боссы} <многострочный_текст>
    user_id = message.from_user.id
    text = message.text or ""
    # ожидаем: /edit <type><space><rest> где rest может содержать переводы строк
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚙️Использование: /edit {персонажи|боссы} имена (каждое имя с новой строки).\nПример:\n/edit персонажи\nЭмбер\nКейа\nЛиза")
        return

    # отделяем type и тело
    second = parts[1]
    tokens = second.split(maxsplit=1)
    typ_token = tokens[0]
    rest = tokens[1] if len(tokens) > 1 else ""
    list_type = normalize_type(typ_token)
    if not list_type:
        bot.reply_to(message, "✖️ Неверный тип. Укажите 'персонажи' или 'боссы' после /edit.")
        return
    if not rest.strip():
        bot.reply_to(message, "❗Пожалуйста, укажите имена после типа. Каждое имя с новой строки.")
        return

    # разбиваем по строкам, фильтруем пустые
    lines = [line.strip() for line in rest.splitlines() if line.strip()]
    if not lines:
        bot.reply_to(message, "✖️ Список пустой. Ожидалось каждое имя с новой строки.")
        return

    chars_map, bosses_map = load_main_lists()
    main_map = chars_map if list_type == "characters" else bosses_map
    other_map = bosses_map if list_type == "characters" else chars_map

    errors = []
    seen = {}
    valid_items = []

    for idx, raw in enumerate(lines, start=1):
        name = raw.strip()
        name_l = name.lower()
        # дубликат в самом запросе
        if name_l in seen:
            errors.append(f"⚠️Строка {idx}: имя '{name}' повторяется (повтор в строке {seen[name_l]}).")
            continue
        seen[name_l] = idx

        # проверка наличия в главных списках
        in_main = name_l in main_map
        in_other = name_l in other_map
        if not in_main and not in_other:
            errors.append(f"⚠️Строка {idx}: '{name}' не найдено в главных списках (персонажи/боссы).")
            continue
        if in_other and not in_main:
            # это имя есть, но в другом типе
            errors.append(f"⚠️Строка {idx}: '{name}' найдено в другом типе (перепутан босс/персонаж).")
            continue

        # всё ок — добавляем каноническое имя
        canonical = main_map.get(name_l)
        valid_items.append(canonical)

    if errors:
        bot.reply_to(message, "✖️ Найдены ошибки. Список НЕ сохранён:\n" + "\n".join(errors))
        return

    # перед сохранением проверим, нет ли дубликатов (на всякий случай) — we've already checked within provided list
    # сохраняем кастомный список
    save_db_list(user_id, list_type, valid_items)
    bot.reply_to(message, f"✔️ Ваш кастомный список {'персонажей' if list_type=='characters' else 'боссов'} успешно обновлён. {len(valid_items)} записей.")

@bot.message_handler(commands=['reset'])
def cmd_reset(message):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚙️Использование: /reset {персонажи|боссы}\nПример: /reset персонажи")
        return
    list_type = normalize_type(parts[1])
    if not list_type:
        bot.reply_to(message, "✖️ Неверный тип. Укажите 'персонажи' или 'боссы'.")
        return
    delete_db_list(user_id, list_type)
    bot.reply_to(message, f"✔️ Ваш кастомный список {'персонажей' if list_type=='characters' else 'боссов'} удалён. Будут использоваться стандартные файлы.")

@bot.message_handler(commands=['show'])
def cmd_show(message):
    # /show персонажи
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚙️Использование: /show {персонажи|боссы}")
        return
    list_type = normalize_type(parts[1])
    if not list_type:
        bot.reply_to(message, "✖️ Неверный тип. Укажите 'персонажи' или 'боссы'.")
        return
    items, is_custom = get_list_for_user(message.from_user.id, list_type)
    header = "📜Ваш кастомный список" if is_custom else "📜Стандартный список"
    if not items:
        bot.reply_to(message, f"{header}: пусто.")
    else:
        # На случай очень длинных списков: ограничиваем вывод по символам/строкам
        preview = "\n".join(items[:500])
        bot.reply_to(message, f"{header} ({len(items)} записей):\n{preview}")

# ---------- Админ/доп команды ----------
@bot.message_handler(commands=['reload'])
def cmd_reload(message):
    bot.reply_to(message, "⚠️Файлы читаются при запросе. Следующие вызовы будут использовать актуальные файлы.")

# ---------- Запуск ----------
if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()