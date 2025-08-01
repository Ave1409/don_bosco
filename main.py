from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
from pymongo import MongoClient
from datetime import datetime
from authlib.integrations.flask_client import OAuth  # Google OAuth
import os
import uuid

site="http://localhost:5000"

app = Flask(__name__)
app.secret_key = "secretkey1234567890"  # Required for session management
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

# OAuth Setup--------------------------------------------
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params={'access_type': 'offline'},
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://www.googleapis.com/oauth2/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    redirect_uri='http://localhost:5000/auth/callback/google'
)

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

@app.route('/api/active-users')
def get_active_users():
    # Optionally augment with more info if you like (e.g. username from DB)
    users = [{'user_id': uid} for uid in user_sid_map.keys()]
    return jsonify(users)

@app.route('/admin')
def admin_dashboard():
    return render_template('admin.html')

@socketio.on('client_location')
def handle_client_location(data):
    user_id = data.get('user_id')
    lat = data.get('lat')
    lon = data.get('lon')

    if not all([user_id, lat, lon]):
        print(f"Incomplete location data received: {data}")
        return

    # The admin listening to this user will be in this room.
    admin_room = f"admin_{user_id}"
    emit('user_location_update',
         {'user_id': user_id, 'lat': lat, 'lon': lon},
         room=admin_room)
    print(f"Location update from {user_id}: {lat}, {lon} -> Relayed to room {admin_room}")

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
    incident = {
        "user_id": json.get('user_id'),
        "timestamp": datetime.now(),
        "type": "panic",
        "level": json.get('level'),
        "auto-dispatch": True
    }
    incidents_col.insert_one(incident)



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
    if 'anonymous_user_id' not in session:
        session['anonymous_user_id'] = str(uuid.uuid4())
    return render_template('index.html', user_id=session['anonymous_user_id'])

# Dashboard smart redirect
@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect('/register')
    user = users_col.find_one({'email': session['email']})
    if not user:
        return redirect('/register')
    return redirect('/user-dashboard')
#register
#Object_ID =

@socketio.on('panic')
def handle_panic_event(data):
    user_id = data.get('user_id')
    print(f"PANIC (highest level of noise) received from user: {user_id}")
    incident = {
        "user_id": user_id,
        "timestamp": datetime.now(),
        "type": "panic",
        "level": data.get("level", "Danger"),
        "auto-dispatch": False # Set to True if auto-dispatch is enabled
    }
    incidents_col.insert_one(incident)

    

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

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    # Check for pre-fill data from Google OAuth
    google_info = session.get('google_oauth_info', None)
    print(f"method: {request.method}")

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        dob = request.form['dob']
        gender = request.form['gender']

        if users_col.find_one({'email': email}):
            # If email exists, show a clear error message on the registration page.
            flash('An account with this email already exists. Please try logging in.', 'error')
            return redirect(url_for('register'))

        new_user_id = str(uuid.uuid4())
        print(f"Registering user: {new_user_id}, email: {email}, phone: {phone}, address: {address}, dob: {dob}, gender: {gender}", flush=True)
        users_col.insert_one({
            "_id": new_user_id,
            "username": username,
            "email": email,
            "phone": phone,
            "address": address,
            "dob": dob,
            "gender": gender,
            "emergency_pressed": 0,
            "registered_at": datetime.now(),
            "last_login": datetime.now()
        })

        # Clear the temporary Google info from session after use
        if 'google_oauth_info' in session:
            session.pop('google_oauth_info', None)

        session['email'] = email
        session['name'] = username

        # flash(f"Welcome, {username}! Your registration was successful.", 'success')
        return redirect('/user-dashboard')

    # Pass Google info to the template on GET requests to pre-fill the form
    return render_template('register.html', google_info=google_info)

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        user = users_col.find_one({"email": email})

        if user:
            session['user'] = {
                "name": user.get('username', 'User'),
                "email": user['email']
            }
            return redirect('/user-dashboard')
        else:
            return "User not found or incorrect credentials", 401

    return render_template('login.html')

# Google Login Start
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect("http://localhost:5000/auth/callback/google")

# Google OAuth Callback
@app.route('/auth/callback/google')
def authorize_google():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()

    email = user_info['email']
    name = user_info.get('name')

    user = users_col.find_one({'email': email})
    if not user:
        # New user: store Google info in session and redirect to full registration form
        session['google_oauth_info'] = {'email': email, 'name': name}
        return redirect(url_for('register'))

    # User exists — update last_login
    users_col.update_one(
        {"email": email},
        {"$set": {"last_login": datetime.now()}}
    )

    session['email'] = email
    session['name'] = user.get('username', name)

    if not all(k in user for k in ['dob', 'gender', 'phone', 'address']):
        return redirect('/complete-profile')

    return redirect('/user-dashboard')

# Complete Profile
@app.route('/complete-profile', methods=['GET', 'POST'])
def complete_profile():
    if 'email' not in session:
        return redirect('/login')

    if request.method == 'POST':
        dob = request.form['dob']
        gender = request.form['gender']
        phone = request.form['phone']
        address = request.form['address']

        users_col.update_one(
            {'email': session['email']},
            {'$set': {
                'dob': dob,
                'gender': gender,
                'phone': phone,
                'address': address,
                'last_login': datetime.now()
            }}
        )
        return redirect('/user-dashboard')

    return render_template('complete-profile.html')

@app.route('/user-dashboard')
def user_dashboard():
    if 'email' not in session:
        return redirect('/login')

    user = users_col.find_one({'email': session['email']})
    if not user:
        return redirect('/register')  # Changed this line to handle first-time users

    # 💡 Map DB fields to HTML-expecting fields
    user['govt_id'] = user.get('username', 'Not set')
    user['account_created'] = user.get('registered_at', 'Not available')
    user['emergency_press_count'] = user.get('emergency_pressed', 0)
    user['last_login'] = user.get('last_login', 'Not recorded')

    # Ensure other fields don't crash the page
    fields = ['phone', 'address', 'dob', 'gender']
    for field in fields:
        user[field] = user.get(field, 'Not set')

    return render_template('user-dashboard.html', user=user)

if __name__ == "__main__":
    socketio.run(app, debug=True)
