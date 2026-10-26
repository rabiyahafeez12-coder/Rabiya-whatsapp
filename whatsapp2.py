import sqlite3
from flask import Flask, render_template_string, request, redirect, session
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.secret_key = 'super_secret_whatsapp_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- SQLite Database Initialization ---
def init_db():
    conn = sqlite3.connect('whatsapp.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            FOREIGN KEY(user1_id) REFERENCES users(id),
            FOREIGN KEY(user2_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- HTML Templates ---
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhatsApp Web - Auth</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: Arial, sans-serif; }
    body { background-color: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
    .auth-card { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); width: 350px; display: flex; flex-direction: column; gap: 15px; }
    h2 { color: #008069; text-align: center; }
    .error { color: #ea4335; font-size: 13px; text-align: center; }
    form { display: flex; flex-direction: column; gap: 10px; }
    input { padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
    button { background-color: #008069; color: white; border: none; padding: 10px; border-radius: 4px; cursor: pointer; font-weight: bold; }
    button.signup { background-color: #25d366; }
  </style>
</head>
<body>
  <div class="auth-card">
    <h2>WhatsApp Web</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    
    <form action="/login" method="POST">
      <h3>Login</h3>
      <input type="text" name="username" placeholder="Username" required autocomplete="off"/>
      <input type="password" name="password" placeholder="Password" required/>
      <button type="submit">Log In</button>
    </form>
    
    <hr>

    <form action="/register" method="POST">
      <h3>Register</h3>
      <input type="text" name="username" placeholder="Choose Username" required autocomplete="off"/>
      <input type="password" name="password" placeholder="Choose Password" required/>
      <button type="submit" class="signup">Sign Up</button>
    </form>
  </div>
</body>
</html>
"""

MAIN_APP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhatsApp Web Clone</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: Arial, sans-serif; }
    body { background-color: #d1d7db; display: flex; justify-content: center; align-items: center; height: 100vh; }
    .app-container { display: flex; width: 90%; max-width: 1200px; height: 90vh; background-color: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); }
    .sidebar { width: 380px; background-color: #f0f2f5; border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; }
    .sidebar-header { padding: 12px 16px; background-color: #008069; color: white; display: flex; justify-content: space-between; align-items: center; }
    .logout-btn { background: #ea4335; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 12px; }
    .section-title { padding: 10px 16px; font-size: 12px; font-weight: bold; color: #008069; text-transform: uppercase; background-color: #e9edef; }
    .add-box { padding: 10px 16px; background: #fff; border-bottom: 1px solid #e0e0e0; display: flex; gap: 8px; }
    .add-box input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
    .add-btn { background-color: #008069; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: bold; }
    .list { overflow-y: auto; flex: 1; }
    .item { display: flex; align-items: center; padding: 12px 16px; background: white; border-bottom: 1px solid #f0f2f5; gap: 10px; cursor: pointer; }
    .item:hover, .item.active { background-color: #f0f2f5; }
    .avatar { width: 40px; height: 40px; border-radius: 50%; background-color: #6b7c85; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0; }
    .info { flex: 1; display: flex; flex-direction: column; }
    .name { font-size: 14px; font-weight: bold; }
    .status { font-size: 12px; color: #667781; }
    .chat-panel { flex: 1; display: flex; flex-direction: column; background-color: #efeae2; }
    .chat-header { padding: 12px 16px; background-color: #f0f2f5; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #e0e0e0; }
    .chat-body { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
    .message { max-width: 60%; padding: 8px 12px; border-radius: 8px; font-size: 14px; word-break: break-word; }
    .message.received { background-color: white; align-self: flex-start; }
    .message.sent { background-color: #d9fdd3; align-self: flex-end; }
    .chat-footer { padding: 10px 16px; background-color: #f0f2f5; display: flex; gap: 10px; }
    .chat-footer input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 8px; outline: none; }
    .send-btn { background-color: #008069; color: white; border: none; padding: 0 20px; border-radius: 8px; cursor: pointer; }
    .error-msg { color: #ea4335; font-size: 12px; padding: 5px 16px; background: #fff; }
  </style>
</head>
<body>
  <div class="app-container">
    <div class="sidebar">
      <div class="sidebar-header">
        <div style="display:flex; align-items:center; gap:10px;">
          <div class="avatar">{{ current_user[0].upper() }}</div>
          <h3>{{ current_user }}</h3>
        </div>
        <a href="/logout" class="logout-btn">Logout</a>
      </div>

      <form action="/start_chat" method="POST" class="add-box">
        <input type="text" name="partner_username" placeholder="Type friend's username..." required autocomplete="off"/>
        <button type="submit" class="add-btn">Chat</button>
      </form>
      {% if error %}
        <div class="error-msg">{{ error }}</div>
      {% endif %}

      <div class="section-title">Chats</div>
      <div class="list">
        {% for contact in contacts %}
          <div class="item {% if active_partner and active_partner.id == contact.id %}active{% endif %}" onclick="location.href='/?chat_user={{ contact.username }}'">
            <div class="avatar">{{ contact.username[0].upper() }}</div>
            <div class="info">
              <div class="name">{{ contact.username }}</div>
              <div class="status">Click to open chat</div>
            </div>
          </div>
        {% else %}
          <div style="padding:15px 16px; font-size:13px; color:#667781;">No chats yet. Type a username above to start chatting!</div>
        {% endfor %}
      </div>
    </div>

    <div class="chat-panel">
      <div class="chat-header">
        {% if active_partner %}
          <div class="avatar">{{ active_partner.username[0].upper() }}</div>
          <div>
            <h3>{{ active_partner.username }}</h3>
            <span style="font-size:12px; color:#667781;">online</span>
          </div>
        {% else %}
          <h3>Select a chat to start messaging</h3>
        {% endif %}
      </div>

      <div class="chat-body" id="chatBody">
        {% if active_partner %}
          {% for msg in messages %}
            <div class="message {% if msg.sender_id == current_user_id %}sent{% else %}received{% endif %}">
              {{ msg.text }}
            </div>
          {% endfor %}
        {% endif %}
      </div>

      {% if active_partner %}
        <div class="chat-footer">
          <input type="text" id="msgInput" placeholder="Type a message..." autocomplete="off"/>
          <button type="button" class="send-btn" onclick="sendMessage()">Send</button>
        </div>
      {% endif %}
    </div>
  </div>

  <script>
    const currentUserId = {{ current_user_id }};
    const activePartnerId = {{ active_partner.id if active_partner else 'null' }};
    const socket = io();

    if (activePartnerId) {
      socket.emit('join', { user_id: currentUserId });

      socket.on('new_message', function(data) {
        if ((data.sender_id === activePartnerId && data.receiver_id === currentUserId) ||
            (data.sender_id === currentUserId && data.receiver_id === activePartnerId)) {
          
          const chatBody = document.getElementById('chatBody');
          const msgDiv = document.createElement('div');
          msgDiv.className = 'message ' + (data.sender_id === currentUserId ? 'sent' : 'received');
          msgDiv.innerText = data.text;
          chatBody.appendChild(msgDiv);
          chatBody.scrollTop = chatBody.scrollHeight;
        }
      });
    }

    function sendMessage() {
      const input = document.getElementById('msgInput');
      const text = input.value.trim();
      if (text && activePartnerId) {
        socket.emit('send_msg', {
          sender_id: currentUserId,
          receiver_id: activePartnerId,
          text: text
        });
        input.value = '';
      }
    }

    document.getElementById('msgInput')?.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') sendMessage();
    });
  </script>
</body>
</html>
"""

# --- Flask Routes ---

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')

    current_user_id = session['user_id']
    current_username = session['username']
    chat_username = request.args.get('chat_user')
    error = request.args.get('error')

    conn = sqlite3.connect('whatsapp.db')
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT u.id, u.username 
        FROM contacts c 
        JOIN users u ON (u.id = c.user1_id OR u.id = c.user2_id)
        WHERE (c.user1_id = ? OR c.user2_id = ?) AND u.id != ?
    ''', (current_user_id, current_user_id, current_user_id))
    contacts = [{'id': row[0], 'username': row[1]} for row in cursor.fetchall()]

    active_partner = None
    messages = []

    if chat_username:
        cursor.execute("SELECT id, username FROM users WHERE LOWER(username) = LOWER(?)", (chat_username,))
        user_row = cursor.fetchone()
        if user_row:
            active_partner = {'id': user_row[0], 'username': user_row[1]}
            
            cursor.execute('''
                SELECT sender_id, receiver_id, text 
                FROM messages 
                WHERE (sender_id = ? AND receiver_id = ?) 
                   OR (sender_id = ? AND receiver_id = ?)
                ORDER BY timestamp ASC
            ''', (current_user_id, active_partner['id'], active_partner['id'], current_user_id))
            
            messages = [{'sender_id': row[0], 'receiver_id': row[1], 'text': row[2]} for row in cursor.fetchall()]

    conn.close()

    return render_template_string(
        MAIN_APP_HTML,
        current_user=current_username,
        current_user_id=current_user_id,
        contacts=contacts,
        active_partner=active_partner,
        messages=messages,
        error=error
    )

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    password = request.form.get('password')
    conn = sqlite3.connect('whatsapp.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        session['user_id'] = cursor.lastrowid
        session['username'] = username
        conn.close()
        return redirect('/')
    except sqlite3.IntegrityError:
        conn.close()
        return render_template_string(LOGIN_HTML, error="Username already exists!")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = sqlite3.connect('whatsapp.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE LOWER(username) = LOWER(?) AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect('/')
        return render_template_string(LOGIN_HTML, error="Invalid credentials")
    
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/start_chat', methods=['POST'])
def start_chat():
    partner_username = request.form.get('partner_username', '').strip()
    current_user_id = session.get('user_id')

    if not partner_username:
        return redirect('/')

    conn = sqlite3.connect('whatsapp.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, username FROM users WHERE LOWER(username) = LOWER(?)", (partner_username,))
    partner = cursor.fetchone()

    if not partner:
        conn.close()
        return redirect('/?error=User+not+found')

    partner_id = partner[0]
    partner_name = partner[1]

    if partner_id == current_user_id:
        conn.close()
        return redirect('/?error=Cannot+chat+with+yourself')

    cursor.execute('''
        SELECT id FROM contacts 
        WHERE (user1_id = ? AND user2_id = ?) OR (user1_id = ? AND user2_id = ?)
    ''', (current_user_id, partner_id, partner_id, current_user_id))
    
    if not cursor.fetchone():
        cursor.execute("INSERT INTO contacts (user1_id, user2_id) VALUES (?, ?)", (current_user_id, partner_id))
        conn.commit()

    conn.close()
    return redirect(f'/?chat_user={partner_name}')

# --- WebSockets for Real-Time Chat ---

@socketio.on('join')
def on_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")

@socketio.on('send_msg')
def handle_message(data):
    sender_id = data['sender_id']
    receiver_id = data['receiver_id']
    text = data['text']

    conn = sqlite3.connect('whatsapp.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (sender_id, receiver_id, text) VALUES (?, ?, ?)", 
                   (sender_id, receiver_id, text))
    conn.commit()
    conn.close()

    emit('new_message', data, room=f"user_{sender_id}")
    emit('new_message', data, room=f"user_{receiver_id}")

import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    socketio.run(app, host='0.0.0.0', port=port)
