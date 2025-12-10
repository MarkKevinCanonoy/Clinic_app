from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
import bcrypt
import jwt
import os
import re 

# --- GLOBAL STATE STORAGE (In-Memory) ---
#chat_states: Dict[int, Dict] = {}

app = FastAPI()

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kurt_cobain', 
    'database': 'school_clinic'
}

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# --- Helper Functions ---
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# JWT conf
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
security = HTTPBearer()

def create_token(user_id: int, role: str, full_name: str) -> str:
    payload = {
        'user_id': user_id,
        'role': role,
        'full_name': full_name,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    return decode_token(token)

def create_default_users():
    """Seed default admins"""
    print("Checking for default admin accounts...")
    conn = get_db()
    cursor = conn.cursor()
    try:
        default_users = [
            {"full_name": "Super Admin", "email": "superadmin@clinic.com", "password": "admin123", "role": "super_admin"},
            {"full_name": "Clinic Admin", "email": "admin@clinic.com", "password": "admin123", "role": "admin"}
        ]
        for user in default_users:
            cursor.execute("SELECT id FROM users WHERE email = %s", (user['email'],))
            if not cursor.fetchone():
                hashed_pw = hash_password(user['password'])
                cursor.execute(
                    "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
                    (user['full_name'], user['email'], hashed_pw, user['role'])
                )
                print(f"Created default user: {user['email']} ({user['role']})")
        conn.commit()
    except Error as e:
        print(f"Error seeding database: {e}")
    finally:
        cursor.close()
        conn.close()

@app.on_event("startup")
def on_startup():
    create_default_users()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class UserRegister(BaseModel):
    full_name: str
    email: EmailStr
    password: str

class AdminCreateUser(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: str 

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class AppointmentCreate(BaseModel):
    appointment_date: str
    appointment_time: str
    service_type: str
    urgency: str
    reason: str
    booking_mode: str = "standard"

class AppointmentUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None

class ChatMessage(BaseModel):
    message: str

# --- API routes ---

@app.post("/api/register")
def register(user: UserRegister):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pw = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, 'student')",
            (user.full_name, user.email, hashed_pw)
        )
        conn.commit()
        return {"message": "Registration successful"}
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/admin/create-user")
def create_admin_user(user: AdminCreateUser, current_user = Depends(get_current_user)):
    if current_user['role'] != 'super_admin':
        raise HTTPException(status_code=403, detail="Only Super Admins can create admin accounts")
    
    if user.role not in ['admin', 'super_admin']:
        raise HTTPException(status_code=400, detail="Invalid role specified")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_pw = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
            (user.full_name, user.email, hashed_pw, user.role)
        )
        conn.commit()
        return {"message": f"User created successfully as {user.role}"}
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/login")
def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE email = %s", (user.email,))
        db_user = cursor.fetchone()
        
        if not db_user or not verify_password(user.password, db_user['password']):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        token = create_token(db_user['id'], db_user['role'], db_user['full_name'])
        
        return {
            "token": token,
            "role": db_user['role'],
            "user_id": db_user['id'],
            "full_name": db_user['full_name']
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/appointments")
def get_appointments(current_user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        if current_user['role'] == 'student':
            cursor.execute("""
                SELECT a.*, u.full_name as student_name
                FROM appointments a
                JOIN users u ON a.student_id = u.id
                WHERE a.student_id = %s
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """, (current_user['user_id'],))
        else:
            cursor.execute("""
                SELECT a.*, u.full_name as student_name, u.email as student_email
                FROM appointments a
                JOIN users u ON a.student_id = u.id
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """)
        
        results = cursor.fetchall()
        for row in results:
            row['appointment_date'] = str(row['appointment_date'])
            row['appointment_time'] = str(row['appointment_time'])
            
        return results
    finally:
        cursor.close()
        conn.close()

@app.post("/api/appointments")
def create_appointment(appointment: AppointmentCreate, current_user = Depends(get_current_user)):
    if current_user['role'] != 'student':
        raise HTTPException(status_code=403, detail="Only students can book appointments")
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        # INSERT matches schema ENUM('Normal', 'Urgent')
        cursor.execute("""
            INSERT INTO appointments (student_id, appointment_date, appointment_time, service_type, urgency, reason, booking_mode, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            current_user['user_id'], 
            appointment.appointment_date, 
            appointment.appointment_time, 
            appointment.service_type, 
            appointment.urgency, 
            appointment.reason, 
            appointment.booking_mode
        ))
        conn.commit()
        return {"message": "Appointment booked successfully", "id": cursor.lastrowid}
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.put("/api/appointments/{appointment_id}")
def update_appointment(appointment_id: int, update: AppointmentUpdate, current_user = Depends(get_current_user)):
    if current_user['role'] not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Only admins can update appointments")
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. check current status first
        cursor.execute("SELECT status FROM appointments WHERE id = %s", (appointment_id,))
        current_appt = cursor.fetchone()
        
        if not current_appt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # 2. plot hole fix: if already completed, stop!
        if update.status == 'completed' and current_appt['status'] == 'completed':
            raise HTTPException(status_code=400, detail="ALREADY_SCANNED")

        # 3. otherwise, update normally
        cursor.execute("""
            UPDATE appointments 
            SET status = %s, admin_note = %s, updated_at = NOW()
            WHERE id = %s
        """, (update.status, update.admin_note, appointment_id))
        conn.commit()
        
        return {"message": "Appointment updated successfully"}
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/appointments/{appointment_id}")
def delete_or_cancel_appointment(appointment_id: int, current_user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT student_id, status FROM appointments WHERE id = %s", (appointment_id,))
        appt = cursor.fetchone()
        
        if not appt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        if current_user['role'] == 'student' and appt['student_id'] != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Not authorized")

        if appt['status'] == 'pending':
             cursor.execute("UPDATE appointments SET status = 'canceled', updated_at = NOW() WHERE id = %s", (appointment_id,))
             message = "Appointment canceled successfully"
        else:
             cursor.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
             message = "Appointment record deleted successfully"
        
        conn.commit()
        return {"message": message}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/users")
def get_users(current_user = Depends(get_current_user)):
    if current_user['role'] != 'super_admin':
        raise HTTPException(status_code=403, detail="Only super admins can view users")
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, full_name, email, role, created_at FROM users ORDER BY created_at DESC")
        results = cursor.fetchall()
        for row in results:
            row['created_at'] = str(row['created_at'])
        return results
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current_user = Depends(get_current_user)):
    if current_user['role'] != 'super_admin':
        raise HTTPException(status_code=403, detail="Only Super Admins can delete users")
    if current_user['user_id'] == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return {"message": "User deleted successfully"}
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# ==========================================
#   logic based chatbot for booking appointments
# ==========================================
# global dictionary to store user states in memory
chat_states = {}

@app.post("/api/chat")
async def chat_booking(chat: ChatMessage, current_user = Depends(get_current_user)):
    """
    Smarter Logic-Based Chatbot.
    Fixed: No more RecursionError.
    """
    
    # 1. Access Control
    if current_user['role'] != 'student':
        return {"response": "Sorry, only students can book appointments.", "requires_action": False}

    user_id = current_user['user_id']
    message = chat.message.strip().lower()

    # 2. Initialize State
    if user_id not in chat_states:
        chat_states[user_id] = {"step": "idle", "data": {}}

    state = chat_states[user_id]
    
    # --- Reset Logic ---
    if any(w in message for w in ["cancel", "stop", "reset", "wrong"]):
        chat_states[user_id] = {"step": "idle", "data": {}}
        return {"response": "Okay, I've cleared everything. 🔄 Start again by saying 'Hi' or 'Book'.", "requires_action": False}

    # ==================================================
    # STEP 1: SMART EXTRACTION (Always runs)
    # ==================================================
    current_data = state["data"]

    # a. Service
    if "consultation" in message: current_data["service_type"] = "Medical Consultation"
    elif "clearance" in message: current_data["service_type"] = "Medical Clearance"

    # b. Urgency
    if "urgent" in message: current_data["urgency"] = "Urgent"
    elif "normal" in message: current_data["urgency"] = "Normal"

    # c. Date
    if "tomorrow" in message:
        current_data["appointment_date"] = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', message)
        if date_match:
            try:
                input_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
                if input_date >= datetime.now().date():
                    current_data["appointment_date"] = date_match.group(1)
            except ValueError: pass

    # d. Time
    # 12-hour (2:30pm)
    ampm_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', message)
    # 24-hour (14:00)
    military_match = re.search(r'(\d{1,2}):(\d{2})(?!\s*(?:am|pm))', message)

    if ampm_match:
        h, m = int(ampm_match.group(1)), int(ampm_match.group(2) or 0)
        p = ampm_match.group(3)
        if 1 <= h <= 12 and 0 <= m <= 59:
            if p == "pm" and h != 12: h += 12
            elif p == "am" and h == 12: h = 0
            current_data["appointment_time"] = f"{h:02d}:{m:02d}:00"
    elif military_match:
        h, m = int(military_match.group(1)), int(military_match.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            current_data["appointment_time"] = f"{h:02d}:{m:02d}:00"

    # e. Reason
    if "because" in message:
        parts = message.split("because", 1)
        if len(parts) > 1: current_data["reason"] = parts[1].strip()
    elif "reason is" in message:
        parts = message.split("reason is", 1)
        if len(parts) > 1: current_data["reason"] = parts[1].strip()
    
    # Special: If we are specifically asking for a reason, take the whole message
    if state["step"] == "asking_reason" and "reason" not in current_data:
        current_data["reason"] = chat.message # take raw message

    chat_states[user_id]["data"] = current_data

    # ==================================================
    # STEP 2: DETERMINE NEXT ACTION
    # ==================================================
    
    # Start flow triggers
    triggers = ["book", "appointment", "schedule", "visit", "consultation", "clearance"]
    
    if state["step"] == "idle":
        if any(w in message for w in ["hi", "hello", "hey"]) and not any(w in message for w in triggers):
            return {"response": "Hello! 👋 I am the Clinic AI.\n\nYou can say 'Book appointment' or give me details like: 'Book medical consultation tomorrow at 2pm'.", "requires_action": False}
        
        if any(w in message for w in triggers) or len(current_data) > 0:
            state["step"] = "check_requirements"

    # ==================================================
    # STEP 3: CHECK WHAT IS MISSING
    # ==================================================
    
    # We always check requirements if not idle/saving
    if state["step"] not in ["idle", "saving"]:
        data = state["data"]
        
        if "service_type" not in data:
            chat_states[user_id]["step"] = "asking_service"
            return {"response": "I can help! 🩺\n\nIs this for a **Medical Consultation** or **Medical Clearance**?", "requires_action": False}
        
        if "appointment_date" not in data:
            chat_states[user_id]["step"] = "asking_date"
            return {"response": f"Okay, a {data['service_type']}. 🗓️\n\nWhat date? (Format: YYYY-MM-DD or say 'tomorrow')", "requires_action": False}

        if "appointment_time" not in data:
            chat_states[user_id]["step"] = "asking_time"
            return {"response": f"Got the date ({data['appointment_date']}). 🕒\n\nWhat time? (e.g., '2pm', '10:00 am', or '14:00')", "requires_action": False}

        if "urgency" not in data:
            chat_states[user_id]["step"] = "asking_urgency"
            return {"response": "Noted. Is this condition **Normal** or **Urgent**?", "requires_action": False}

        if "reason" not in data:
            chat_states[user_id]["step"] = "asking_reason"
            return {"response": "Almost done! 📝\n\nPlease briefly state the **reason** for your visit.", "requires_action": False}

        # If we reach here, we have EVERYTHING.
        state["step"] = "saving"

    # ==================================================
    # STEP 4: SAVE
    # ==================================================
    if state["step"] == "saving":
        data = state["data"]
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO appointments (student_id, appointment_date, appointment_time, service_type, urgency, reason, booking_mode, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'ai_chatbot', 'pending')
            """, (
                user_id, data['appointment_date'], data['appointment_time'], 
                data['service_type'], data['urgency'], data['reason']
            ))
            conn.commit()
            
            # Nice display time
            display_time = datetime.strptime(data['appointment_time'], "%H:%M:%S").strftime("%I:%M %p")

            response_msg = (
                f"🎉 **Success!** Booked your {data['service_type']}.\n\n"
                f"📅 **Date:** {data['appointment_date']}\n"
                f"🕒 **Time:** {display_time}\n"
                f"📝 **Reason:** {data['reason']}\n\n"
                "See you soon! 💙"
            )
            chat_states[user_id] = {"step": "idle", "data": {}}
            return {"response": response_msg, "requires_action": False}

        except Exception as e:
            print(f"DB Error: {e}")
            return {"response": "System error saving appointment. Please try again.", "requires_action": False}
        finally:
            if 'cursor' in locals(): cursor.close()
            if 'conn' in locals(): conn.close()

    return {"response": "I didn't quite get that. Try saying 'reset' or check your spelling.", "requires_action": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)