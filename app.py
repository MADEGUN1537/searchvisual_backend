from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime
import bcrypt

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["https://madegun1537.github.io", "http://localhost:8080"])

OPENVERSE_API_BASE = "https://api.openverse.engineering/v1"
PEXELS_API_KEY = "F6EjgGWyOfrdxCaWKJ7jUOhL8Eg3BxVc4UHZdkoSGXUjUgGx3ph3Ogyf"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"

# NEW PostgreSQL connection setup
DATABASE_URL = "postgresql://search_visuals_user:8Ncg4D9HQ62ODlppXzyZF9rfuPKKlYAg@dpg-d06ur52li9vc73eopb2g-a/search_visuals"

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    print("Initializing Database...")
    conn = get_db_connection()
    cur = conn.cursor()

    # Create users table if not exists
    cur.execute(''' 
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')

    # Create search_history table if not exists
    cur.execute(''' 
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            media_type TEXT NOT NULL,
            search_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized!")

# Initialize the database when the application starts
init_db()

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        origin = request.headers.get('Origin')  # Get the origin dynamically
        if origin in ["https://madegun1537.github.io", "http://localhost:8080"]:
            response.headers.add("Access-Control-Allow-Origin", origin)
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    if not username or not email or not password or not confirm_password:
        return jsonify({"error": "All fields are required."}), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, hashed_password))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Signup successful!"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Email already exists."}), 409
    except Exception as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'OK'})
        origin = request.headers.get('Origin')
        if origin in ["http://localhost:8080", "https://madegun1537.github.io"]:
            response.headers.add("Access-Control-Allow-Origin", origin)
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            # Ensure user["password"] is correctly interpreted as a byte string
            stored_password_hash = user["password"].encode('utf-8')  # Encode to bytes if not already
            if bcrypt.checkpw(password.encode('utf-8'), stored_password_hash):  # Compare as byte strings
                return jsonify({"message": "Login successful!", "user_id": user["id"]}), 200
            else:
                return jsonify({"error": "Invalid credentials."}), 401
        else:
            return jsonify({"error": "Invalid credentials."}), 401

    except Exception as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500

@app.route('/search-history', methods=['GET'])
def get_search_history():
    user_id = request.args.get('user_id')

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT query, media_type, search_time FROM search_history WHERE user_id = %s ORDER BY search_time DESC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        history = [{"query": row["query"], "media_type": row["media_type"], "search_time": row["search_time"]} for row in rows]
        return jsonify({"history": history}), 200

    except Exception as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500

@app.route('/search', methods=['GET'])
def search_media():
    query = request.args.get('query')
    media_type = request.args.get('media_type')
    user_id = request.args.get('user_id')

    if not query or not media_type or not user_id:
        return jsonify({"error": "Missing query, media_type or user_id"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO search_history (user_id, query, media_type) VALUES (%s, %s, %s)", (user_id, query, media_type))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500

    if media_type == "images":
        response = requests.get(f"{OPENVERSE_API_BASE}/images", params={"q": query, "page_size": 10})
        if response.status_code == 200:
            results = response.json().get("results", [])
            return jsonify({"results": [{"url": item["url"], "title": item["title"]} for item in results]}), 200
        else:
            return jsonify({"error": "Failed to fetch from Openverse"}), 500

    elif media_type == "audio":
        response = requests.get(f"{OPENVERSE_API_BASE}/audio", params={"q": query, "page_size": 10})
        if response.status_code == 200:
            results = response.json().get("results", [])
            return jsonify({"results": [{"url": item["url"], "title": item["title"]} for item in results]}), 200
        else:
            return jsonify({"error": "Failed to fetch from Openverse"}), 500

    elif media_type == "videos":
        headers = {"Authorization": PEXELS_API_KEY}
        response = requests.get(PEXELS_VIDEO_API, headers=headers, params={"query": query, "per_page": 5})
        if response.status_code == 200:
            data = response.json()
            results = []
            for video in data.get("videos", []):
                video_url = video["video_files"][0]["link"] if video["video_files"] else None
                title = video.get("user", {}).get("name", "Pexels Video")
                results.append({"url": video_url, "title": title})
            return jsonify({"results": results}), 200
        else:
            return jsonify({"error": "Failed to fetch from Pexels"}), 500

    else:
        return jsonify({"error": "Invalid media type"}), 400

if __name__ == '__main__':
    app.run(debug=True)
