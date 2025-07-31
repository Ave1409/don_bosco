from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from pymongo import MongoClient
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = "secretkey1234567890"  # Required for session management
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize SocketIO with CORS allowed for testing
socketio = SocketIO(app, cors_allowed_origins='*')

# MongoDB Setup
client = MongoClient("mongodb://localhost:27017/")
db = client["petalsafe"]
incidents_col = db["incidents"]
users_col = db["users"]

# Dictionary to keep track of user_id -> sid mapping
user_sid_map = {}

# Dictionary to track admin rooms joined, if needed
admins = set()  # Optionally maintain connected admin SIDs


@socketio.on('connect_user')
def handle_connect_user(data):
    user_id = data.get('user_id')
    if not user_id:
        emit('error', {'message': 'No user_id provided'})
        return
    # Save mapping
    user_sid_map[user_id] = request.sid
    # User joins their private room (room named after user_id)
    join_room(user_id)
    print(f"User connected: user_id={user_id}, sid={request.sid}")

@socketio.on('connect_admin')
def handle_connect_admin():
    # Optionally keep track of admin connections
    admins.add(request.sid)
    print(f"Admin connected: sid={request.sid}")

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    # Remove from user_sid_map if exists
    users_to_remove = [uid for uid, s in user_sid_map.items() if s == sid]
    for uid in users_to_remove:
        user_sid_map.pop(uid, None)
        print(f"User disconnected: user_id={uid}, sid={sid}")
    # Remove admin if this sid is admin
    if sid in admins:
        admins.remove(sid)
        print(f"Admin disconnected: sid={sid}")

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    user_id = data.get('user_id')
    chunk = data.get('chunk')
    if not user_id or not chunk:
        print(f"Invalid audio_chunk data received: {data}")
        return

    # For persistence, you might want to save chunks to disk/db here (not shown)
    # Forward audio chunk to admin(s) that have joined this user's room 
    # We define a room for admin listening, e.g. "admin_<user_id>"
    admin_room = f"admin_{user_id}"
    emit('audio_chunk', {'user_id': user_id, 'chunk': chunk}, room=admin_room)
    # Optionally print for debug:
    # print(f"Relayed audio chunk for user_id {user_id} to room {admin_room}")

@socketio.on('request_listen')
def admin_listen_to_user(data):
    user_id = data.get('user_id')
    if not user_id:
        emit('error', {'message': 'No user_id provided for listen request'})
        return
    admin_sid = request.sid
    # Admin joins room to receive user's audio chunks
    room_name = f"admin_{user_id}"
    join_room(room_name)
    print(f"Admin {admin_sid} joined listening room: {room_name}")
    emit('listen_confirm', {'room': room_name})

# Existing event handlers for rescue, help, safe, auto-dispatch
@socketio.on('send_rescue')
def handle_rescue_event(json):
    print('received rescue event: ' + str(json))
    # add your logic here

@socketio.on('auto_dispatch')
def handle_auto_dispatch(json):
    print('received auto-dispatch event: ' + str(json))
    # add your logic here

@socketio.on('send_help')
def handle_help_event(json):
    print('received help event: ' + str(json))
    # add your logic here

@socketio.on('send_safe')
def handle_safe_event(json):
    print('received safe event: ' + str(json))
    # add your logic here

@app.route('/')
def home():
    user_id = str(uuid.uuid4())
    return render_template('index.html', user_id=user_id)

@app.route('/api/upload-audio', methods=['POST'])
def upload_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file part"}), 400

    file = request.files['audio']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        # Get extension from filename
        _, extension = os.path.splitext(file.filename)
        filename = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension or '.dat'}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        print(f"Audio file saved to {filepath}")
        return jsonify({"success": True, "message": "File uploaded successfully", "filename": filename}), 200

if __name__ == "__main__":
    socketio.run(app, debug=True)
