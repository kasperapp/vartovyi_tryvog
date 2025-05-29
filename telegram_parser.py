# telegram_parser.py
import asyncio
import sqlite3
from datetime import datetime
from telethon.sync import TelegramClient
from telethon.tl.types import Channel
import telethon.events # Важливо, щоб було імпортовано telethon.events

# --- КОНФІГУРАЦІЯ ---
# Отримай ці значення з my.telegram.org
API_ID = 23288039
API_HASH = 'f45f02eced51590641157a60d7b9a97e'

SESSION_NAME = 'my_session'
DATABASE_NAME = 'vartovyi_tryvoh.db'

TARGET_CHANNELS = [
    # Приклад: @username каналів
    '@golovneua_live',
    '@kudy_letyt',
    '@kpszsu',
    '@povitryanatrivogaaa',
    '@odesa_golovne',
    '@raketna_neb',
    '@kherson_monitoring',
    '@raketa_trevoga',
    '@Ukrainian_Intelligence',
    '@radar_raketaa',
    '@war_raketaua',
    '@raketa_svitlo',
    '@vanek_nikolaev',
    '@war_monitor',
    '@mon1tor_ua',
    '@SK_DM_SK',
    '@poltava_golovne',
    '@zp_golovne',
    '@gnilayachereha',
    '@Slavyansk_info',
    '@truexapoltava',
    '@strategicontrol',
    '@sumy_main',
    '@sumygo',
    '@sumy_novyny',
    '@sumyliketop',
    '@sumitruexa',
    '@sumy_sumy1',
    '@totallzrada',
    '@shostkainfo',
    '@sumyregion',
    '@hlukhivcity',
    '@suspilnesumy',
    '@news_sumy24',
    '@donbassnew',
    '@eRadarrua',
    '@suspilnezhytomyr',
    '@blacklist_of_vinn',
    '@VinnytsiaODA',
    '@info_zp',
    '@tipove_rivne',
    '@zhytomyr_glvn',
    '@lutsk_tipical',
    '@vinnextnews',
    '@vinnytsia_golovne',
    '@chernivtsi_main',
    '@volyn_golovne_ua',
    '@chernihiv_golovne',
    '@kyiv_golovne',
    '@lviv_golovne',
    '@rivne_golovne',
    '@zahid_golovne_ua',
    '@goodchernivtsi',
    '@zhytomyr_operativ',
    '@truexazhitomir',
    '@vinnytsiarealll',
    '@vinnicatruexa',
    '@tvoi_cherkasy',
    '@eye_ukrainew',
    '@namezhy',
    '@suspilne_vinnytsia',
    '@chernivcitruexa',
    '@vn20minut',
    '@onlinevinn',
    '@newsvinn1',
    '@avimonitor',
    '@vinnytskaODA',
    '@vinnitsa_info',
    '@educationfreeua',
    '@vmroficial',
    '@morgunovofficial',
    '@rocket_danger_lviv',
    '@police_su_region',
    '@vinnpol',
    '@zp_radar',
    '@patrolpolice_vinnytsia',
    '@bayraktarmedia',
    '@rivne_svitlo_voda',
    '@lviv_svitlo_voda_tryvoga',

    # Додайте інші канали за необхідності
]

PRIORITY_KEYWORDS_TRIGGER = [' Гучно в області', 'ракета', 'вибух', 'шахед', 'ОВА', 'повітряна'] # Змінено ОВА
PRIORITY_KEYWORDS_RESET = ['відбій', 'чисто', 'скасували', 'відбою']
CITY_KEYWORDS = [
    'київ', 'харків', 'одеса', 'львів', 'дніпро', 'запоріжжя', 'вінниця', 'полтава', 'чернігів',
    'суми', 'херсон', 'миколаїв', 'житомир', 'черкаси', 'кропивницький', 'рівне', 'луцьк',
    'тернопіль', 'ужгород', 'івано-франківськ', 'чернівці', 'хмельницький', 'краматорськ',
    'кременчук', 'кривий ріг',
    'запорізькій', 'київській', 'одеській', 'львівській', 'дніпропетровській', 'харківській',
    'полтавській', 'сумській', 'черкаській', 'хмельницькій', 'вінницькій', 'житомирській',
    'рівненській', 'тернопільській', 'закарпатській', 'івано-франківській', 'чернівецькій',
    'чернігівській', 'миколаївській', 'херсонській', 'кропивницькій', 'донецькій', 'луганській',
    # Додайте інші міста/області, якщо потрібно
]
# --- КІНЕЦЬ КОНФІГУРАЦІЇ ---

# --- ФУНКЦІЇ ДЛЯ ЗБЕРІГАННЯ ДАНИХ ---
def save_message(message_data):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO messages (
                message_id, channel_id, channel_title, message_text,
                published_at, is_priority, linked_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            message_data['message_id'],
            message_data['channel_id'],
            message_data['channel_title'],
            message_data['message_text'],
            message_data['published_at'],
            int(message_data['is_priority']),
            message_data['linked_event_id'] # Тепер linked_event_id завжди буде присутнім (може бути None)
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Помилка при збереженні повідомлення: {e}")
        return None
    finally:
        conn.close()

def save_event(event_data):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO events (
                event_type, keywords, start_time, end_time,
                first_reported_message_id, first_reported_channel_title
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            event_data['event_type'],
            event_data.get('keywords'),
            event_data['start_time'],
            event_data.get('end_time'),
            event_data.get('first_reported_message_id'),
            event_data.get('first_reported_channel_title')
        ))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Помилка при збереженні події: {e}")
        return None
    finally:
        conn.close()

def update_event_end_time(event_id, end_time):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE events SET end_time = ? WHERE id = ?
        ''', (end_time, event_id))
        conn.commit()
        print(f"Оновлено час закінчення події {event_id} на {end_time}")
    except sqlite3.Error as e:
        print(f"Помилка при оновленні часу закінчення події: {e}")
    finally:
        conn.close()

def get_active_event(event_type):
    """
    Повертає активну (незавершену) подію певного типу.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM events
        WHERE event_type = ? AND end_time IS NULL
        ORDER BY start_time DESC LIMIT 1
    """, (event_type,))
    event = cursor.fetchone()
    conn.close()
    return dict(event) if event else None

# --- ЛОГІКА ПАРСИНГУ ТА ОБРОБКИ ПОВІДОМЛЕНЬ ---
async def process_message(event):
    if not event.message or not event.message.text:
        return

    message_text = event.message.text.lower()
    is_priority = False
    event_type = None
    linked_event_id = None
    
    channel_title = event.chat.title if event.chat else f"ID: {event.chat_id}"
    
    # Визначення міст/областей для ключових слів події
    detected_cities = [city for city in CITY_KEYWORDS if city in message_text]
    event_keywords_str = ', '.join(detected_cities) if detected_cities else None

    is_alarm_trigger = any(kw in message_text for kw in PRIORITY_KEYWORDS_TRIGGER)
    is_alarm_reset = any(kw in message_text for kw in PRIORITY_KEYWORDS_RESET)

    if is_alarm_trigger and not is_alarm_reset:
        is_priority = True
        event_type = 'air_raid'
        
        active_event = get_active_event('air_raid')
        
        if active_event:
            linked_event_id = active_event['id']
            # print(f"Повідомлення про тривогу пов'язане з існуючою подією ID: {linked_event_id}")
        else:
            # Це перше повідомлення про нову тривогу
            print(f"Нова повітряна тривога виявлена каналом {channel_title}. Створюємо подію...")
            event_id = save_event({
                'event_type': 'air_raid',
                'keywords': event_keywords_str,
                'start_time': datetime.now().isoformat(),
                'first_reported_message_id': None, # Буде оновлено після збереження повідомлення
                'first_reported_channel_title': channel_title
            })
            linked_event_id = event_id
            print(f"Створено нову подію тривоги ID: {event_id}")
            # Оновлюємо first_reported_message_id для новоствореної події
            if event_id:
                conn = sqlite3.connect(DATABASE_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE events SET first_reported_message_id = ? WHERE id = ?", (event.message.id, event_id)) # Зберігаємо Telethon message ID
                conn.commit()
                conn.close()


    elif is_alarm_reset:
        is_priority = True
        event_type = 'air_raid_reset' # Можна мати окремий тип для відбою, або просто використовувати 'air_raid'
        
        active_event = get_active_event('air_raid')
        if active_event:
            update_event_end_time(active_event['id'], datetime.now().isoformat())
            linked_event_id = active_event['id'] # Пов'язуємо відбій з існуючою подією
            print(f"Відбій тривоги виявлено. Оновлено подію ID: {linked_event_id}")
        else:
            # Якщо відбій прийшов, але активної тривоги не було зареєстровано (наприклад, парсер перезапустився)
            # Ми все одно можемо зареєструвати це як пріоритетне повідомлення.
            print("Відбій тривоги, але активної події не знайдено.")


    # Якщо це не тривога/відбій, але містить інші пріоритетні слова (наприклад, вибух)
    # І при цьому linked_event_id ще не встановлений (щоб не перезаписати тривогу)
    if not is_priority and any(kw in message_text for kw in PRIORITY_KEYWORDS_TRIGGER): # Тут тільки тригерні, без відбою
        is_priority = True
        event_type = 'general_priority_news' # Для вибухів, ракет без оголошення тривоги
        # Ми можемо створити нову подію для цього, або залишити linked_event_id NULL
        # Для простоти, поки що не створюємо нові події для кожного "вибуху", якщо це не тривога.
        # Можна додати логіку для створення "вибухових" подій, якщо потрібно.

    # Збираємо дані повідомлення
    message_data = {
        'message_id': event.message.id,
        'channel_id': event.chat_id,
        'channel_title': channel_title,
        'message_text': event.message.text,
        'published_at': event.message.date.isoformat(),
        'is_priority': is_priority,
        'linked_event_id': linked_event_id
    }
    
    message_db_id = save_message(message_data)
    if message_db_id:
        print(f"Збережено повідомлення ID {message_db_id} від {message_data['channel_title']} ({message_data['published_at']}): '{message_data['message_text'][:50]}...' (Priority: {is_priority}, Event ID: {linked_event_id})")
    else:
        print(f"Помилка або дублікат повідомлення від {message_data['channel_title']}: '{message_data['message_text'][:50]}...'")


# --- ГОЛОВНА ФУНКЦІЯ ПАРСЕРА ---
async def main():
    # init_db() # Залишаємо це в database_setup.py для кращої організації

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    print("Підключення до Telegram...")
    await client.start()
    print("Підключено!")

    channels = []
    for target in TARGET_CHANNELS:
        try:
            entity = await client.get_entity(target)
            if isinstance(entity, Channel):
                channels.append(entity)
                print(f"Додано канал: {entity.title} ({entity.id})")
            else:
                print(f"Помилка: {target} не є каналом або групою. Тип: {type(entity)}")
        except Exception as e:
            print(f"Не вдалося отримати канал {target}: {e}")
    
    if not channels:
        print("Не знайдено жодного цільового каналу. Перевірте TARGET_CHANNELS.")
        return

    @client.on(telethon.events.NewMessage(chats=channels))
    async def handler(event):
        await process_message(event)

    print("Парсер запущено. Очікування нових повідомлень...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())