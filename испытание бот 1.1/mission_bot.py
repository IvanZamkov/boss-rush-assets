import telebot
from telebot.types import InlineQueryResultArticle, InputTextMessageContent
import random
import uuid
import os
import traceback

BOT_TOKEN = "8518491353:AAHOdT0RY8Dlt7kkpXR7speVtiSfTZmVxYM"

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

def load_list(filename):
    if not os.path.exists(filename):
        print(f"[WARN] Файл {filename} не найден.")
        return []
    with open(filename, "r", encoding="utf-8") as f:
        items = [line.strip() for line in f if line.strip()]
    return items

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOSSES_FILE = os.path.join(BASE_DIR, "bosses.txt")
CHARS_FILE = os.path.join(BASE_DIR, "characters.txt")

def load_list(filename):
    print(f"[DEBUG] Текущее рабочее место (cwd): {os.getcwd()}")
    print(f"[DEBUG] Директория скрипта: {BASE_DIR}")
    print(f"[DEBUG] Ищем файл: {filename}")
    try:
        print(f"[DEBUG] Содержимое папки скрипта: {os.listdir(BASE_DIR)}")
    except Exception as e:
        print(f"[DEBUG] не удалось прочитать список файлов в {BASE_DIR}: {e}")

    if not os.path.exists(filename):
        print(f"[ERROR] Файл не найден: {filename}")
        try:
            open(filename, "a", encoding="utf-8").close()
            print(f"[INFO] Создан пустой файл: {filename} (создайте в него имена вручную)")
        except Exception as e:
            print(f"[ERROR] Не удалось создать файл {filename}: {e}")
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            items = [line.strip() for line in f if line.strip()]
        print(f"[DEBUG] Загружено {len(items)} строк из {filename}")
        return items
    except Exception as e:
        print(f"[ERROR] При чтении {filename} произошла ошибка: {e}")
        return []

bosses = load_list(BOSSES_FILE)
characters = load_list(CHARS_FILE)



def make_message(num_chars: int) -> str:
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

THUMBS = {
    1: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_1.jpg",
    2: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_2.jpg",
    3: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_3.jpg",
    4: "https://raw.githubusercontent.com/IvanZamkov/boss-rush-assets/main/thumb_4.jpg",
}

@bot.inline_handler(lambda query: True)
def inline_query_handler(inline_query):
    try:
        results = []

        for n in range(1, 5):
            try:
                text = make_message(n)
                content = InputTextMessageContent(text)
                if n == 1:
                    title = "Одиночное испытание"
                    description = ""
                else:
                    title = f"Отряд из {n} персонажей"
                    description = f""
                thumb = THUMBS.get(n)
                kwargs = {
                    "id": str(uuid.uuid4()),
                    "title": title,
                    "input_message_content": content,
                    "description": description
                }
                if thumb:
                    if thumb.startswith("https://"):
                        kwargs["thumbnail_url"] = thumb
                    else:
                        print(f"[WARN] Миниатюра для {n} не использована (не https): {thumb}")

                result = InlineQueryResultArticle(**kwargs)
                results.append(result)

            except Exception as e_item:
                # В случае ошибки для конкретной карточки — логируем и продолжаем
                print(f"[ERROR] Ошибка при создании результата для {n}: {e_item}")
                traceback.print_exc()
                # Не добавляем этот результат, но продолжаем собирать другие

        # Если по какой-то причине список пуст — вернём fallback-результат
        if not results:
            fallback = InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="(Ошибка) Генерация недоступна",
                input_message_content=InputTextMessageContent("⚠️ Сейчас не получилось сгенерировать результат. Попробуйте позже."),
                description="Проблема на стороне бота"
            )
            results = [fallback]

        # Отправляем все собранные результаты (cache_time=0 удобно при тестировании)
        bot.answer_inline_query(inline_query.id, results, cache_time=0)

        print(f"[INFO] inline_query handled, returned {len(results)} items for qid={inline_query.id}")

    except Exception as e:
        # Ловим глобальные ошибки inline handler'а
        print("[CRITICAL] Ошибка inline handler'а:", e)
        traceback.print_exc()
        # в крайнем случае — возвращаем маленький fallback, чтобы клиент не завис
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

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.reply_to(message, "Тестовое сообщение")

@bot.message_handler(commands=['reload'])
def cmd_reload(message):
    global bosses, characters
    bosses = load_list(BOSSES_FILE)
    characters = load_list(CHARS_FILE)
    bot.reply_to(message, f"Списки перезагружены. Боссов: {len(bosses)}, персонажей: {len(characters)}")

if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()
