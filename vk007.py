import vk_api
import time
import datetime
import uuid
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from collections import defaultdict
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

# Определение базовой директории
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Инициализация VK API
VK_TOKEN = os.getenv("VK_TOKEN", "YOUR_VK_SERVICE_OR_USER_TOKEN_HERE")
VK_API_URL = "https://api.vk.com/method/"

def init_vk_api():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    return vk_session.get_api()

# Получение информации о пользователе
def get_user_info(vk, user_id):
    try:
        user = vk.users.get(user_ids=user_id, fields='online, last_seen, first_name, last_name')
        return user[0] if user else None
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе {user_id}: {e}")
        return None

# Получение списка друзей
def get_friends(vk, user_id):
    try:
        friends = vk.friends.get(user_id=user_id, fields='online, last_seen')
        return friends.get('items', []) if isinstance(friends, dict) else []
    except Exception as e:
        logger.error(f"Ошибка при получении друзей пользователя {user_id}: {e}")
        return []

# Проверка статуса онлайна
def check_online_status(vk, user_id, friends):
    data = {'timestamp': datetime.datetime.now(), 'target': {'id': user_id, 'online': 0}}
    friends_data = {}
    
    user_info = get_user_info(vk, user_id)
    if user_info:
        data['target']['online'] = user_info.get('online', 0)
        data['target']['last_seen'] = user_info.get('last_seen', {}).get('time', 0)
        data['target']['name'] = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}"
    
    for friend in friends:
        friend_id = friend['id']
        friends_data[friend_id] = {
            'online': friend.get('online', 0),
            'last_seen': friend.get('last_seen', {}).get('time', 0),
            'name': f"{friend.get('first_name', '')} {friend.get('last_name', '')}"
        }
    data['friends'] = friends_data
    return data

# Анализ совпадений
def analyze_coincidences(data_list, threshold=0.8):
    coincidences = defaultdict(lambda: {'online_matches': 0, 'offline_matches': 0, 'total_checks': 0})
    
    for data in data_list:
        target_online = data['target']['online']
        target_last_seen = data['target']['last_seen']
        
        for friend_id, friend_data in data['friends'].items():
            friend_online = friend_data['online']
            friend_last_seen = friend_data['last_seen']
            
            coincidences[friend_id]['total_checks'] += 1
            if target_online and friend_online:
                coincidences[friend_id]['online_matches'] += 1
            if not target_online and not friend_online and abs(target_last_seen - friend_last_seen) < 300:
                coincidences[friend_id]['offline_matches'] += 1
    
    suspicious = {}
    for friend_id, stats in coincidences.items():
        online_ratio = stats['online_matches'] / stats['total_checks'] if stats['total_checks'] > 0 else 0
        offline_ratio = stats['offline_matches'] / stats['total_checks'] if stats['total_checks'] > 0 else 0
        if online_ratio > threshold or offline_ratio > threshold:
            suspicious[friend_id] = {'online_ratio': online_ratio, 'offline_ratio': offline_ratio}
    
    return suspicious

# Вычисление интервалов онлайн
def calculate_online_intervals(data_list):
    intervals = []
    data_list.sort(key=lambda x: x['timestamp'])
    current_start = None
    for data in data_list:
        ts = data['timestamp']
        online = data['target']['online']
        if online:
            if current_start is None:
                current_start = ts
        else:
            if current_start is not None:
                end = ts
                duration = (end - current_start).total_seconds() / 60
                intervals.append({'start': current_start.strftime('%Y-%m-%d %H:%M:%S'), 'end': end.strftime('%Y-%m-%d %H:%M:%S'), 'duration': f"{duration:.2f} минут"})
                current_start = None
    if current_start is not None:
        end = datetime.datetime.now()
        duration = (end - current_start).total_seconds() / 60
        intervals.append({'start': current_start.strftime('%Y-%m-%d %H:%M:%S'), 'end': end.strftime('%Y-%m-%d %H:%M:%S'), 'duration': f"{duration:.2f} минут (продолжается)"})
    return intervals

# Генерация HTML-отчёта с детальной статистикой
def generate_html_report(suspicious, friends, target_id, target_name, data_list):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Отчёт о мониторинге активности VK</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body {{ background-color: #1a1a1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }}
            .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #2d2d2d; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(255, 255, 255, 0.05); }}
            .table {{ background-color: #2d2d2d; border-radius: 8px; overflow: hidden; }}
            .table th, .table td {{ padding: 12px; border-bottom: 1px solid #444; }}
            .table th {{ background-color: #3a3a3a; }}
            .highlight {{ background-color: #991b1b; color: #ffffff; padding: 2px 6px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="text-3xl font-bold text-center">Отчёт о мониторинге онлайна VK</h1>
                <p class="text-center mt-2">Цель: <b>{target_name}</b> (ID: {target_id})</p>
                <p class="text-center text-gray-400">Сгенерировано: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <h2 class="text-2xl mt-6 mb-4">Подозрительные совпадения активности (вероятные диалоги)</h2>
            <p class="text-gray-400 mb-3">Совпадения активности цели и друзей выше 80%. Подсвечены совпадения по одновременному онлайну и выходу из сети.</p>
            <table class="table w-full text-left">
                <thead>
                    <tr>
                        <th>Имя</th>
                        <th>ID</th>
                        <th>Совпадения по онлайну</th>
                        <th>Совпадения по оффлайну</th>
                        <th>Возможный диалог?</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for friend_id, stats in suspicious.items():
        friend = next((f for f in friends if f['id'] == friend_id), None)
        if friend:
            name = f"{friend.get('first_name', '')} {friend.get('last_name', '')}"
            online_class = 'class="highlight"' if stats['online_ratio'] > 0.8 else ''
            offline_class = 'class="highlight"' if stats['offline_ratio'] > 0.8 else ''
            possible_dialog = 'Да' if stats['online_ratio'] > 0.8 else 'Нет'
            html_content += f"""
                    <tr>
                        <td>{name}</td>
                        <td>{friend_id}</td>
                        <td><span {online_class}>{stats['online_ratio']:.2%}</span></td>
                        <td><span {offline_class}>{stats['offline_ratio']:.2%}</span></td>
                        <td>{possible_dialog}</td>
                    </tr>
            """
    
    html_content += """
                </tbody>
            </table>
    """

    # Интервалы онлайн цели
    intervals = calculate_online_intervals(data_list)
    html_content += """
            <h2 class="text-2xl mt-6 mb-4">Интервалы нахождения в сети</h2>
            <table class="table w-full text-left">
                <thead>
                    <tr>
                        <th>Начало сессии</th>
                        <th>Окончание сессии</th>
                        <th>Продолжительность</th>
                    </tr>
                </thead>
                <tbody>
    """
    for interval in intervals:
        html_content += f"""
                <tr>
                    <td>{interval['start']}</td>
                    <td>{interval['end']}</td>
                    <td>{interval['duration']}</td>
                </tr>
        """
    html_content += """
                </tbody>
            </table>
    """

    # Детальный лог мониторинга
    html_content += """
            <h2 class="text-2xl mt-6 mb-4">Детальный журнал проверок</h2>
            <table class="table w-full text-left">
                <thead>
                    <tr>
                        <th>Время проверки</th>
                        <th>Онлайн цели</th>
                        <th>Последний визит</th>
                        <th>Друзей онлайн</th>
                        <th>Детали совпадений</th>
                    </tr>
                </thead>
                <tbody>
    """
    for data in data_list:
        ts = data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        target_online = 'Да' if data['target']['online'] else 'Нет'
        target_last_seen = datetime.datetime.fromtimestamp(data['target']['last_seen']).strftime('%Y-%m-%d %H:%M:%S') if data['target']['last_seen'] else 'N/A'
        total_friends = len(data['friends'])
        online_friends = sum(1 for f in data['friends'].values() if f['online'])
        debug_details = []
        for friend_id, f in data['friends'].items():
            highlight = ' <span class="highlight">(совпадение!)</span>' if (data['target']['online'] and f['online']) or (not data['target']['online'] and not f['online'] and abs(data['target']['last_seen'] - f['last_seen']) < 300) else ''
            if highlight or f['online']:
                status = 'Онлайн' if f['online'] else 'Оффлайн'
                debug_details.append(f"{f['name']} ({friend_id}): {status}{highlight}")
        debug_str = '<br>'.join(debug_details) if debug_details else 'Нет активных совпадений'
        html_content += f"""
                <tr>
                    <td>{ts}</td>
                    <td>{target_online}</td>
                    <td>{target_last_seen}</td>
                    <td>{online_friends} / {total_friends}</td>
                    <td>{debug_str}</td>
                </tr>
        """
    html_content += """
                </tbody>
            </table>
    """

    # Статистика по друзьям
    html_content += """
            <h2 class="text-2xl mt-6 mb-4">Общая статистика по друзьям</h2>
            <table class="table w-full text-left">
                <thead>
                    <tr>
                        <th>Имя</th>
                        <th>ID</th>
                        <th>Проверок</th>
                        <th>Был онлайн</th>
                        <th>Средняя разница визита (сек)</th>
                    </tr>
                </thead>
                <tbody>
    """
    friend_stats = defaultdict(lambda: {'checks': 0, 'online': 0, 'last_seen_deltas': []})
    for data in data_list:
        target_last_seen = data['target']['last_seen']
        for friend_id, f in data['friends'].items():
            friend_stats[friend_id]['checks'] += 1
            if f['online']:
                friend_stats[friend_id]['online'] += 1
            if f['last_seen'] and target_last_seen:
                delta = abs(f['last_seen'] - target_last_seen)
                friend_stats[friend_id]['last_seen_deltas'].append(delta)
    
    for friend_id, stats in friend_stats.items():
        friend = next((f for f in friends if f['id'] == friend_id), None)
        if friend:
            name = f"{friend.get('first_name', '')} {friend.get('last_name', '')}"
            avg_delta = sum(stats['last_seen_deltas']) / len(stats['last_seen_deltas']) if stats['last_seen_deltas'] else 0
            html_content += f"""
                    <tr>
                        <td>{name}</td>
                        <td>{friend_id}</td>
                        <td>{stats['checks']}</td>
                        <td>{stats['online']}</td>
                        <td>{avg_delta:.2f}</td>
                    </tr>
            """
    html_content += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    report_filename = f"report_{uuid.uuid4().hex[:10]}.html"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return report_path

# Хранилище для активных задач слежки в памяти
tracking_tasks = {}

# Обработчик команды /start
@router.message(Command("start"))
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать слежку", callback_data='start_tracking')],
        [InlineKeyboardButton(text="Остановить слежку", callback_data='stop_tracking')]
    ])
    await message.reply(
        "👋 Добро пожаловать в бот аналитики активности VK!\nВыберите действие:",
        reply_markup=keyboard
    )

# Обработчик callback-кнопок
@router.callback_query()
async def button(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    
    if callback.data == 'start_tracking':
        await callback.message.reply("Введите ID или username пользователей VK (через запятую):")
        tracking_tasks[chat_id] = {'state': 'waiting_for_ids'}

    elif callback.data == 'stop_tracking':
        if chat_id in tracking_tasks and tracking_tasks[chat_id].get('running', False):
            tracking_tasks[chat_id]['running'] = False
            if 'timer_message_id' in tracking_tasks[chat_id]:
                message_id = tracking_tasks[chat_id]['timer_message_id']
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="Слежка остановлена досрочно.",
                    reply_markup=None
                )
            await callback.message.reply("Слежка остановлена!")
        else:
            await callback.message.reply("Нет активных задач слежки.")

    elif callback.data == 'update_timer':
        if chat_id in tracking_tasks:
            task = tracking_tasks[chat_id]
            if task.get('running', False):
                start_time = task.get('start_time', time.time())
                duration = task['duration']
                remaining = duration - (time.time() - start_time)
                if remaining > 0:
                    min_rem = int(remaining // 60)
                    sec_rem = int(remaining % 60)
                    new_text = f"⏳ Слежка в процессе.\nОсталось: {min_rem} мин. {sec_rem} сек."
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=callback.message.message_id,
                        text=new_text,
                        reply_markup=callback.message.reply_markup
                    )
                else:
                    new_text = "Слежка завершена."
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=callback.message.message_id,
                        text=new_text,
                        reply_markup=None
                    )
                    task['running'] = False
            else:
                new_text = "Слежка завершена или остановлена."
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=callback.message.message_id,
                    text=new_text,
                    reply_markup=None
                )

    elif callback.data.startswith('duration_'):
        duration = int(callback.data.split('_')[1])
        user_ids = tracking_tasks.get(chat_id, {}).get('user_ids', [])
        
        if not user_ids:
            await callback.message.reply("Ошибка: ID пользователей не указаны.")
            return
        
        tracking_tasks[chat_id] = {'user_ids': user_ids, 'duration': duration, 'running': True}
        await callback.message.reply(
            f"🚀 Слежка начата для пользователей: {', '.join(map(str, user_ids))}\nДлительность: {duration // 60} мин."
        )
        asyncio.create_task(monitor_online_job(chat_id, user_ids, duration))

# Обработчик ввода ID
@router.message()
async def handle_message(message: Message):
    chat_id = message.chat.id
    if chat_id in tracking_tasks and tracking_tasks[chat_id].get('state') == 'waiting_for_ids':
        user_ids = [uid.strip() for uid in message.text.split(',') if uid.strip()]
        tracking_tasks[chat_id]['user_ids'] = user_ids
        tracking_tasks[chat_id]['state'] = 'waiting_for_duration'
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="10 минут", callback_data='duration_600')],
            [InlineKeyboardButton(text="30 минут", callback_data='duration_1800')],
            [InlineKeyboardButton(text="1 час", callback_data='duration_3600')],
            [InlineKeyboardButton(text="3 часа", callback_data='duration_10800')],
            [InlineKeyboardButton(text="8 часов", callback_data='duration_28800')],
            [InlineKeyboardButton(text="12 часов", callback_data='duration_43200')],
            [InlineKeyboardButton(text="24 часа", callback_data='duration_86400')]
        ])
        await message.reply("Выберите длительность слежки:", reply_markup=keyboard)

# Задача циклического мониторинга
async def monitor_online_job(chat_id, user_ids, duration):
    try:
        vk = init_vk_api()
    except Exception as e:
        logger.error(f"Не удалось инициализировать VK API: {e}")
        await bot.send_message(chat_id=chat_id, text=f"Ошибка подключения к VK API: {e}")
        return

    start_time = time.time()
    tracking_tasks[chat_id]['start_time'] = start_time
    all_data = defaultdict(list)
    
    remaining = duration - (time.time() - start_time)
    min_rem = int(remaining // 60)
    sec_rem = int(remaining % 60)
    text = f"⏳ Слежка начата для: {', '.join(map(str, user_ids))}.\nОсталось: {min_rem} мин. {sec_rem} сек."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обновить таймер", callback_data='update_timer')],
        [InlineKeyboardButton(text="Остановить слежку", callback_data='stop_tracking')]
    ])
    timer_msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    tracking_tasks[chat_id]['timer_message_id'] = timer_msg.message_id
    
    while time.time() - start_time < duration and tracking_tasks.get(chat_id, {}).get('running', False):
        for user_id in user_ids:
            try:
                friends = get_friends(vk, user_id)
                data = check_online_status(vk, user_id, friends)
                all_data[user_id].append(data)
            except Exception as e:
                logger.error(f"Ошибка при мониторинге пользователя {user_id}: {e}")
        
        await asyncio.sleep(300)  # Интервал проверки (5 минут)
        
        if tracking_tasks.get(chat_id, {}).get('running', False):
            remaining = duration - (time.time() - start_time)
            if remaining > 0:
                min_rem = int(remaining // 60)
                sec_rem = int(remaining % 60)
                new_text = f"⏳ Слежка в процессе.\nОсталось: {min_rem} мин. {sec_rem} сек."
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=timer_msg.message_id,
                        text=new_text,
                        reply_markup=keyboard
                    )
                except Exception:
                    pass
    
    if tracking_tasks.get(chat_id, {}).get('running', False):
        for user_id in user_ids:
            try:
                suspicious = analyze_coincidences(all_data[user_id])
                user_info = get_user_info(vk, user_id)
                target_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}" if user_info else f"User {user_id}"
                friends = get_friends(vk, user_id)
                report_path = generate_html_report(suspicious, friends, user_id, target_name, all_data[user_id])
                
                await bot.send_document(
                    chat_id=chat_id,
                    document=FSInputFile(report_path),
                    caption=f"📊 Отчёт по пользователю {target_name} (ID: {user_id})"
                )
            except Exception as e:
                logger.error(f"Ошибка при генерации отчёта для {user_id}: {e}")
                await bot.send_message(chat_id=chat_id, text=f"Ошибка при генерации отчёта для {user_id}: {str(e)}")
        
        try:
            new_text = "✅ Слежка завершена. Отчёты сформированы и отправлены."
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=timer_msg.message_id,
                text=new_text,
                reply_markup=None
            )
        except Exception:
            pass
        
    if chat_id in tracking_tasks:
        del tracking_tasks[chat_id]

async def main():
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or VK_TOKEN == "YOUR_VK_SERVICE_OR_USER_TOKEN_HERE":
        logger.warning("ВНИМАНИЕ: Заполните переменные BOT_TOKEN и VK_TOKEN в файле .env!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
