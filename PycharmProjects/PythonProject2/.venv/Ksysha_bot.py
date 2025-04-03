import sqlite3
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler,
    Filters, CallbackContext, ConversationHandler
)

TOKEN = ''
JSON_PATH = "" # Путь к файлу JSON с терминами


# --- Инициализация базы данных ---
def init_db():
    """Создает таблицу, если её нет, и загружает слова из JSON."""
    conn = sqlite3.connect('words.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            translation TEXT NOT NULL,
            correct_answers INTEGER DEFAULT 0,
            incorrect_answers INTEGER DEFAULT 0
        )
    ''')

    # Удаление старых данных
    cursor.execute("DELETE FROM words")

    # Загрузка правильного JSON
    try:
        with open("", "r", encoding="utf-8") as f:
            words = json.load(f)
        for entry in words:
            cursor.execute("INSERT OR IGNORE INTO words (word, translation) VALUES (?, ?)",
                           (entry['latin'], entry['translation']))
        print("Термины успешно загружены в базу данных.")
    except Exception as e:
        print(f"Ошибка загрузки JSON: {e}")

    conn.commit()
    conn.close()
# --- Функции работы с БД ---
def get_random_word():
    """Возвращает случайное слово и его перевод."""
    conn = sqlite3.connect('words.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, word, translation FROM words ORDER BY RANDOM() LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return row


def update_score(word_id: int, correct: bool = True):
    """Обновляет статистику ответов."""
    conn = sqlite3.connect('words.db')
    cursor = conn.cursor()
    if correct:
        cursor.execute('UPDATE words SET correct_answers = correct_answers + 1 WHERE id = ?', (word_id,))
    else:
        cursor.execute('UPDATE words SET incorrect_answers = incorrect_answers + 1 WHERE id = ?', (word_id,))
    conn.commit()
    conn.close()


# --- Обработчики команд ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Привет! Я бот-Quizlet.\n\n"
        "Выберите режим:\n"
        "/flashcards - флеш-карты\n"
        "/test - тестирование\n"
        "/add - добавить новое слово"
    )


def flashcards(update: Update, context: CallbackContext):
    """Режим флеш-карт."""
    word_entry = get_random_word()
    if not word_entry:
        update.message.reply_text("Словарь пуст. Добавьте слова через /add.")
        return
    word_id, word, translation = word_entry
    context.user_data['current_flashcard'] = {'id': word_id, 'word': word, 'translation': translation}
    update.message.reply_text(f"Слово: {word}\n\nНажмите /show, чтобы увидеть перевод.")


def show_answer(update: Update, context: CallbackContext):
    """Показывает перевод текущей карточки."""
    if 'current_flashcard' not in context.user_data:
        update.message.reply_text("Нет активной карточки. Используйте /flashcards.")
        return
    card = context.user_data['current_flashcard']
    update.message.reply_text(f"Перевод: {card['translation']}\n\nНажмите /correct или /incorrect.")


def correct(update: Update, context: CallbackContext):
    if 'current_flashcard' in context.user_data:
        update_score(context.user_data['current_flashcard']['id'], correct=True)
        update.message.reply_text("Правильно! Следующее слово:")
        del context.user_data['current_flashcard']
        flashcards(update, context)  # Сразу запускаем следующую карточку
    else:
        update.message.reply_text("Нет активной карточки. Введите /flashcards для новой.")

def incorrect(update: Update, context: CallbackContext):
    if 'current_flashcard' in context.user_data:
        update_score(context.user_data['current_flashcard']['id'], correct=False)
        update.message.reply_text("Неправильно! Следующее слово:")
        del context.user_data['current_flashcard']
        flashcards(update, context)  # Сразу запускаем следующую карточку
    else:
        update.message.reply_text("Нет активной карточки. Введите /flashcards для новой.")


def test_mode(update: Update, context: CallbackContext):
    """Запускает тест с вариантами ответа."""
    word_entry = get_random_word()
    if not word_entry:
        update.message.reply_text("Словарь пуст. Добавьте слова через /add.")
        return
    word_id, word, translation = word_entry
    options = [translation]

    conn = sqlite3.connect('words.db')
    cursor = conn.cursor()
    cursor.execute('SELECT translation FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3', (word_id,))
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        options.append(row[0])
    random.shuffle(options)

    context.user_data['current_test'] = {'id': word_id, 'word': word, 'correct_translation': translation}
    keyboard = [[InlineKeyboardButton(opt, callback_data=opt)] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(f"Переведите слово: {word}", reply_markup=reply_markup)


def button_handler(update: Update, context: CallbackContext):
    """Обработчик нажатий на кнопки в тестовом режиме."""
    query = update.callback_query
    query.answer()
    if 'current_test' not in context.user_data:
        query.edit_message_text(text="Тест не активен. Попробуйте /test.")
        return
    test_data = context.user_data['current_test']
    chosen_option = query.data
    if chosen_option == test_data['correct_translation']:
        update_score(test_data['id'], correct=True)
        query.edit_message_text(text=f"Правильно! Перевод: {test_data['correct_translation']}")
    else:
        update_score(test_data['id'], correct=False)
        query.edit_message_text(text=f"Неправильно! Ответ: {test_data['correct_translation']}")
    del context.user_data['current_test']


# --- Добавление нового слова ---
ADD_WORD = 1


def add(update: Update, context: CallbackContext):
    update.message.reply_text("Введите новое слово в формате:\nслово - перевод\nнапример: apple - яблоко")
    return ADD_WORD


def add_word_response(update: Update, context: CallbackContext):
    text = update.message.text
    if " - " in text:
        word, translation = map(str.strip, text.split(" - "))
        conn = sqlite3.connect('words.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO words (word, translation) VALUES (?, ?)", (word, translation))
        conn.commit()
        conn.close()
        update.message.reply_text(f"Слово '{word}' добавлено!")
    else:
        update.message.reply_text("Неверный формат. Используйте: слово - перевод")
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Добавление отменено.")
    return ConversationHandler.END


# --- Основная функция ---
def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("flashcards", flashcards))
    dp.add_handler(CommandHandler("show", show_answer))
    dp.add_handler(CommandHandler("correct", correct))
    dp.add_handler(CommandHandler("incorrect", incorrect))
    dp.add_handler(CommandHandler("test", test_mode))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(ConversationHandler(entry_points=[CommandHandler('add', add)],
                                       states={ADD_WORD: [
                                           MessageHandler(Filters.text & ~Filters.command, add_word_response)]},
                                       fallbacks=[CommandHandler('cancel', cancel)]))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
