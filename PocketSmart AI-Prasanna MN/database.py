import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = "pocketsmart.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT,
        hashed_password TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)
    
    # Recommendations history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recommendations (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        recommendation_type TEXT NOT NULL,
        input_data TEXT NOT NULL,
        input_summary TEXT NOT NULL,
        result_summary TEXT NOT NULL,
        full_result TEXT NOT NULL,
        FOREIGN KEY (username) REFERENCES users (username)
    )
    """)
    
    conn.commit()
    conn.close()

def save_user(id: str, username: str, email: str, full_name: Optional[str], hashed_password: str):
    conn = get_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO users (id, username, email, full_name, hashed_password, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (id, username, email, full_name, hashed_password, created_at))
    conn.commit()
    conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def add_recommendation_history(
    username: str,
    recommendation_type: str,
    input_data: Dict[str, Any],
    result: Dict[str, Any],
    rec_id: Optional[str] = None
) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    if not rec_id:
        rec_id = str(uuid.uuid4())
    
    timestamp = datetime.utcnow().strftime("%b %d, %Y, %I:%M %p")
    
    # Generate concise input and result summaries
    budget = input_data.get("total_budget", 0)
    remaining = result.get("remaining_budget", 0)
    
    if recommendation_type == "home":
        rooms = []
        if input_data.get("has_living_room"): rooms.append("Living Room")
        if input_data.get("has_kitchen"): rooms.append("Kitchen")
        if input_data.get("has_bedroom"): rooms.append("Bedroom")
        rooms_str = ", ".join(rooms) if rooms else "General"
        input_summary = f"Rooms: {rooms_str} | Lights: {input_data.get('num_lights', 0)}, Fans: {input_data.get('num_fans', 0)}"
        result_summary = f"Total Budget: ₹{budget:,.0f} | Remaining: ₹{remaining:,.0f}"
    elif recommendation_type == "party":
        party_type = input_data.get("party_type", "Party")
        guests = input_data.get("num_guests", 0)
        input_summary = f"Type: {party_type} | Guests: {guests}"
        result_summary = f"Total Budget: ₹{budget:,.0f} | Remaining: ₹{remaining:,.0f}"
    elif recommendation_type == "jewelry":
        occasion = input_data.get("occasion", "Occasion")
        has_image = "Yes" if input_data.get("image") or input_data.get("has_image") else "No"
        input_summary = f"Occasion: {occasion} | Outfit Image: {has_image}"
        result_summary = f"Total Budget: ₹{budget:,.0f} | Remaining: ₹{remaining:,.0f}"
    else:
        input_summary = f"Budget: ₹{budget:,.0f}"
        result_summary = f"Remaining: ₹{remaining:,.0f}"
        
    cursor.execute("""
    INSERT INTO recommendations (id, username, timestamp, recommendation_type, input_data, input_summary, result_summary, full_result)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rec_id,
        username,
        timestamp,
        recommendation_type,
        json.dumps(input_data),
        input_summary,
        result_summary,
        json.dumps(result)
    ))
    conn.commit()
    conn.close()
    return rec_id

def get_user_recommendations(username: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, username, timestamp, recommendation_type as type, input_data, input_summary as input, result_summary as summary, full_result
    FROM recommendations
    WHERE username = ?
    ORDER BY rowid DESC
    """, (username,))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["input_data"] = json.loads(d["input_data"])
        except Exception:
            pass
        try:
            d["full_result"] = json.loads(d["full_result"])
        except Exception:
            pass
        results.append(d)
    return results

def get_recommendation_by_id(rec_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, username, timestamp, recommendation_type as type, input_data, input_summary as input, result_summary as summary, full_result
    FROM recommendations
    WHERE id = ?
    """, (rec_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["input_data"] = json.loads(d["input_data"])
        except Exception:
            pass
        try:
            d["full_result"] = json.loads(d["full_result"])
        except Exception:
            pass
        return d
    return None

# Initialize database schema on module load
init_db()
