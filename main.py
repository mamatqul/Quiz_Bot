from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import mysql.connector
import constants as c
from random import shuffle


bot = Bot(c.token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Form(StatesGroup):
    question = State()
    answers = State()


@dp.message_handler(commands=['send'])
async def start(message: types.Message):
    if message.chat.id == c.admin:
        await Form.question.set()
        await message.answer("Отправьте сообщение с вопросом (текст и/или фото)\n[/exit] - Отмена")


@dp.message_handler(state=Form.question, content_types=['text', 'photo'])
async def process_name(message: types.Message, state: FSMContext):
    if message.text == "/exit":
        await message.reply("Отменено!")
        await state.finish()
        return
    try: photo = message.photo[-1].file_id
    except IndexError: photo = None
    async with state.proxy() as data:
        if photo is None: data['question'] = [message.text, photo]
        else:  data['question'] = [message.caption, photo]
    await Form.next()
    await message.answer("Отправьте ответы на вопрос через запятую, первый - правильный")


@dp.message_handler(state=Form.answers)
async def send_poll(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['answers'] = message.text
    await state.finish()

    with open("count.txt", "r") as f: count = str(int(f.read()) + 1)
    with open("count.txt", "wt") as f: f.write(count)
    conn = mysql.connector.connect(host=c.host, user=c.user, passwd=c.password, database=c.db)
    cursor = conn.cursor(buffered=True)
    insertQuery = "INSERT INTO ans_correct (ans_id, ans_text) VALUES (%s, %s)"
    cursor.executemany(insertQuery, [(count, str(message.text.split(',')[0]))])
    conn.commit()
    conn.close()

    key = types.InlineKeyboardMarkup()
    try:
        but_1 = types.InlineKeyboardButton(message.text.split(',')[0], callback_data=count + "1")
        but_2 = types.InlineKeyboardButton(message.text.split(',')[1], callback_data=count + "2")
        but_3 = types.InlineKeyboardButton(message.text.split(',')[2], callback_data=count + "3")
        but_4 = types.InlineKeyboardButton(message.text.split(',')[3], callback_data=count + "4")
    except IndexError:
        await message.reply("Неправильный ввод!")
        return
    answers = [but_1, but_2, but_3, but_4]
    shuffle(answers)
    key.add(answers[0], answers[1])
    key.add(answers[2], answers[3])
    if data['question'][1] is None:
        await bot.send_message(c.channel, data['question'][0], reply_markup=key)
    else:
        await bot.send_photo(c.channel, caption=data['question'][0], photo=data['question'][1], reply_markup=key)


@dp.callback_query_handler(lambda callback_query: True)
async def callback_handler(callback_query: types.CallbackQuery):
    question = callback_query.data[:-1]
    answer = callback_query.data[-1:]
    conn = mysql.connector.connect(host=c.host, user=c.user, passwd=c.password, database=c.db)
    cursor = conn.cursor(buffered=True)
    findUserQuery = f"SELECT EXISTS (SELECT ID FROM ans_log WHERE user_id=(%s) AND (answer BETWEEN {question}1 AND {question}4))"
    checkQuery = "SELECT EXISTS (SELECT ID FROM ans_log WHERE user_id=(%s) AND answer=(%s))"
    cursor.execute(findUserQuery, [callback_query.from_user.id])
    exists = cursor.fetchone()[0]
    if exists == 1:
        cursor.executemany(checkQuery, [(callback_query.from_user.id, callback_query.data)])
        check = cursor.fetchone()[0]
        if check == 0:
            await bot.answer_callback_query(callback_query.id, "Вы уже отвечали!", show_alert=False)
            conn.close()
        else:
            await send_reply(cursor, conn, question, answer, callback_query)
        return
    else:
        await send_reply(cursor, conn, question, answer, callback_query, True)


async def send_reply(cursor, conn, question, answer, callback_query, insert=False):
    getCorrectAnswerQuery = "SELECT ans_text FROM ans_correct WHERE ans_id=(%s)"
    getCountQuery = "SELECT COUNT(*) FROM ans_log WHERE answer=(%s)"
    getCountAllQuery = f"SELECT COUNT(*) FROM ans_log WHERE (answer BETWEEN {question}1 AND {question}4)"
    insertQuery = "INSERT INTO ans_log (user_id, answer) VALUES (%s, %s)"
    if insert:
        cursor.executemany(insertQuery, [(callback_query.from_user.id, callback_query.data)])
        conn.commit()
    cursor.execute(getCorrectAnswerQuery, [question])
    correct = cursor.fetchone()[0]
    cursor.execute(getCountQuery, [callback_query.data])
    count = cursor.fetchone()[0]
    cursor.execute(getCountAllQuery)
    count_all = cursor.fetchone()[0]
    conn.close()
    text = ""
    if answer == "1":
        text += "✅ Правильно!\n"
    else:
        text += f"❌ Неправильно!\nПравильный ответ: {correct}\n\n"
    text += "Ответили так же: {} чел. ({}%)".format(count, int(count * 100 / count_all))
    await bot.answer_callback_query(callback_query.id, text, show_alert=True)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
