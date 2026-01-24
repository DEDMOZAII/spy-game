from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room, emit
import random
import string
from game_data import GAME_DATA

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='threading')

# Хранилище данных игры
rooms = {}

def generate_room_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if code not in rooms:
            return code

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/game/<room_code>')
def game(room_code):
    if room_code not in rooms:
        return redirect(url_for('index'))
    return render_template('game.html', room_code=room_code)

# SocketIO Events

@socketio.on('create_room')
def on_create_room(data):
    username = data['username']
    room_code = generate_room_code()
    rooms[room_code] = {
        'players': {},
        'state': 'lobby',
        'word': None,
        'category': None,
        'spy_id': None,
        'start_time': None
    }
    join_room(room_code)
    rooms[room_code]['players'][request.sid] = {
        'name': username,
        'role': None,
        'word': None,
        'is_spy': False
    }
    emit('room_created', {'room_code': room_code, 'players': list(rooms[room_code]['players'].values())}, room=room_code)
    emit('join_success', {'room_code': room_code, 'username': username, 'is_admin': True})

@socketio.on('join_room')
def on_join_room(data):
    username = data['username']
    room_code = data.get('room_code', '').upper()
    
    if room_code not in rooms:
        emit('error', {'message': 'Комната не найдена'})
        return
    
    join_room(room_code)
    rooms[room_code]['players'][request.sid] = {
        'name': username,
        'role': None,
        'word': None,
        'is_spy': False
    }
    
    player_names = [p['name'] for p in rooms[room_code]['players'].values()]
    emit('update_player_list', {'players': player_names}, room=room_code)
    emit('join_success', {'room_code': room_code, 'username': username, 'is_admin': False})

@socketio.on('start_game')
def on_start_game(data):
    room_code = data['room_code']
    if room_code not in rooms:
        return

    # Выбор категории и слова
    category = random.choice(list(GAME_DATA.keys()))
    word = random.choice(GAME_DATA[category])
    all_words = GAME_DATA[category] # Список всех слов для подсказки

    rooms[room_code]['word'] = word
    rooms[room_code]['category'] = category
    rooms[room_code]['state'] = 'playing'
    
    player_sids = list(rooms[room_code]['players'].keys())
    if not player_sids:
        return

    spy_sid = random.choice(player_sids)
    rooms[room_code]['spy_id'] = spy_sid
    
    for sid in player_sids:
        if sid == spy_sid:
            rooms[room_code]['players'][sid]['is_spy'] = True
            role_info = {
                'is_spy': True, 
                'word': '???', 
                'role': 'Шпион', 
                'category': category,
                'possible_words': all_words
            }
        else:
            rooms[room_code]['players'][sid]['is_spy'] = False
            rooms[room_code]['players'][sid]['word'] = word
            role_info = {
                'is_spy': False, 
                'word': word, 
                'role': 'Мирный', 
                'category': category,
                'possible_words': all_words
            }
        
        emit('game_started', role_info, room=sid)

@socketio.on('disconnect')
def on_disconnect():
    for room_code, room_data in rooms.items():
        if request.sid in room_data['players']:
            # Удаляем игрока из списка активных подключений
            del room_data['players'][request.sid]
            
            # Обновляем список для оставшихся
            player_names = [p['name'] for p in room_data['players'].values()]
            emit('update_player_list', {'players': player_names}, room=room_code)
            
            # Не удаляем комнату сразу, чтобы игроки могли переподключиться
            # if not room_data['players']:
            #     del rooms[room_code]
            break

if __name__ == '__main__':
    # allow_unsafe_werkzeug=True нужен для работы сокетов в threading режиме на dev-сервере
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)