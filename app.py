# app.py
import sqlite3
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time

# --- КОНФІГУРАЦІЯ ---
DATABASE_NAME = 'vartovyi_tryvoh.db'
# --- КІНЕЦЬ КОНФІГУРАЦІЇ ---

app = Flask(__name__)
app.config['SECRET_KEY'] = 'some_secret_key_for_flask'
socketio = SocketIO(app, cors_allowed_origins="*")

# Функція для отримання повідомлень з бази даних
def get_messages_from_db(limit=50, priority_only=False):
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Змінюємо запит, щоб долучати інформацію про подію (для "Хто перший?")
    # та визначати затримку відносно початку події.
    query = """
        SELECT
            m.*,
            e.first_reported_channel_title AS event_first_reporter_channel,
            STRFTIME('%s', m.published_at) - STRFTIME('%s', e.start_time) AS delay_seconds_from_event_start
        FROM messages m
        LEFT JOIN events e ON m.linked_event_id = e.id
    """
    params = []
    conditions = []

    if priority_only:
        conditions.append("m.is_priority = 1")
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY m.published_at DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    messages = cursor.fetchall()
    conn.close()
    
    # Перетворюємо об'єкти Row у звичайні словники та додаємо логіку "Хто перший?"
    result_messages = []
    for row in messages:
        message = dict(row)
        # Якщо повідомлення пов'язане з подією і є інформація про першого репортера
        if message['event_first_reporter_channel']:
            message['first_reporter'] = {
                'channel_title': message['event_first_reporter_channel'],
                # Затримка: 0, якщо це повідомлення є першим або якщо час публікації співпадає
                'delay_seconds': int(message['delay_seconds_from_event_start']) if message['delay_seconds_from_event_start'] > 0 else 0
            }
        result_messages.append(message)
    return result_messages

# Функція для отримання інформації про активну тривогу для фронтенду при підключенні
def get_current_alarm_state():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Знаходимо активну (незавершену) повітряну тривогу
    cursor.execute("""
        SELECT * FROM events
        WHERE event_type = 'air_raid' AND end_time IS NULL
        ORDER BY start_time DESC LIMIT 1
    """)
    event = cursor.fetchone()
    conn.close()
    if event:
        return {
            'is_active': True,
            'start_time': event['start_time'] # ISO формат часу
        }
    return {'is_active': False}

# Маршрут для головної сторінки дашборду
@app.route('/')
def index():
    return render_template('index.html')

# API маршрут для отримання повідомлень через HTTP (для першого завантаження сторінки)
@app.route('/api/messages')
def api_messages():
    priority_only = False
    if 'priority' in request.args and request.args['priority'].lower() == 'true':
        priority_only = True
    messages = get_messages_from_db(limit=100, priority_only=priority_only)
    return jsonify(messages)

# Функція для моніторингу нових повідомлень в БД та відправки через WebSocket
def monitor_db_for_new_messages():
    last_message_id = 0
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM messages")
        result = cursor.fetchone()
        if result and result[0] is not None:
            last_message_id = result[0]
        conn.close()
    except Exception as e:
        print(f"Помилка при отриманні останнього ID повідомлення: {e}")

    print(f"Початок моніторингу бази даних з останнього ID: {last_message_id}")

    while True:
        try:
            conn = sqlite3.connect(DATABASE_NAME)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Вибираємо нові повідомлення з долученою інформацією про подію
            cursor.execute("""
                SELECT
                    m.*,
                    e.first_reported_channel_title AS event_first_reporter_channel,
                    STRFTIME('%s', m.published_at) - STRFTIME('%s', e.start_time) AS delay_seconds_from_event_start
                FROM messages m
                LEFT JOIN events e ON m.linked_event_id = e.id
                WHERE m.id > ? ORDER BY m.id ASC
            """, (last_message_id,))
            new_messages = cursor.fetchall()
            conn.close()

            if new_messages:
                for row in new_messages:
                    message = dict(row)
                    if message['event_first_reporter_channel']:
                        message['first_reporter'] = {
                            'channel_title': message['event_first_reporter_channel'],
                            'delay_seconds': int(message['delay_seconds_from_event_start']) if message['delay_seconds_from_event_start'] > 0 else 0
                        }
                    socketio.emit('new_message', message)
                    last_message_id = max(last_message_id, message['id'])
                print(f"Відправлено {len(new_messages)} нових повідомлень через WebSocket. Оновлено last_message_id до {last_message_id}.")
            
            time.sleep(1) # Перевіряємо базу даних кожну секунду

        except sqlite3.Error as e:
            print(f"Помилка при читанні БД в моніторингу: {e}")
            time.sleep(5)
        except Exception as e:
            print(f"Загальна помилка в monitor_db_for_new_messages: {e}")
            time.sleep(5)


@socketio.on('connect')
def test_connect():
    print('Client connected to WebSocket!')
    # Надсилаємо останні повідомлення при підключенні
    initial_messages = get_messages_from_db(limit=50)
    emit('initial_messages', initial_messages)
    
    # Надсилаємо поточний стан тривоги
    alarm_state = get_current_alarm_state()
    emit('alarm_state', alarm_state)


@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected from WebSocket')

if __name__ == '__main__':
    db_monitor_thread = threading.Thread(target=monitor_db_for_new_messages, daemon=True)
    db_monitor_thread.start()
    
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)