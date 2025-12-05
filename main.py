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
chat_states: Dict[int, Dict] = {}

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
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE appointments 
            SET status = %s, admin_note = %s, updated_at = NOW()
            WHERE id = %s
        """, (update.status, update.admin_note, appointment_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
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
        cursor.execute("SELECT id, full_name, email, role, created_at FROM users WHERE role IN ('admin', 'super_admin')")
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

@app.post("/api/chat")
async def chat_booking(chat: ChatMessage, current_user = Depends(get_current_user)):
    """
    Enhanced Logic-Based Chatbot with "Personality"
    """
    
    # access control part
    if current_user['role'] != 'student':
        return {"response": "Sorry, only students can book appointments.", "requires_action": False}

    user_id = current_user['user_id']
    message = chat.message.strip().lower()

    # initialize state
    if user_id not in chat_states:
        chat_states[user_id] = {"step": "idle", "data": {}}

    state = chat_states[user_id]
    step = state["step"]

    # cancel
    if "cancel" in message or "stop" in message or "reset" in message:
        chat_states[user_id] = {"step": "idle", "data": {}}
        return {"response": "Okay, I've canceled the current booking process. 🔄 Say 'Hi' or 'Book' to start again.", "requires_action": False}

    response_text = ""
    
    # ==================================================
    # handles start, greetings, thanks
    # ==================================================
    if step == "idle":
        # to trigger booking
        if "book" in message or "appointment" in message or "schedule" in message:
            chat_states[user_id]["step"] = "asking_service"
            response_text = "I'd love to help you with that! 🩺 \n\nWhat type of service do you need? (e.g., Medical Consultation, Medical Clearance)"
        
        # greetings
        elif "hello" in message or "hi" in message or "hey" in message:
            response_text = "Hello! 👋 I am the Clinic AI. I can help you schedule a visit.\n\nJust say 'Book appointment' to get started!"
        
        # gratitude - handles "Thank you" after booking
        elif any(word in message for word in ["thank", "thanks", "tysm", "salamat"]):
            response_text = "You're very welcome! 😊 I'm happy I could help. \n\nStay healthy! Let me know if you need anything else."
        
        # closings
        elif "bye" in message or "goodbye" in message:
            response_text = "Goodbye! Take care of yourself! 👋"

        # general agreement
        elif any(word in message for word in ["ok", "okay", "cool", "great", "nice"]):
            response_text = "Great! 👍 I'm here if you need to book a schedule."

        # fallback
        else:
            response_text = "I'm listening! 👂 You can say 'Book appointment' to start, or just say 'Hello'."

    # ==================================================
    # asking service
    # ==================================================
    elif step == "asking_service":
        if "medical" in message or "dental" in message or "consultation" in message or "clearance" in message:
            service_val = "Medical Consultation"
            if "clearance" in message: service_val = "Medical Clearance"
            
            chat_states[user_id]["data"]["service_type"] = service_val
            chat_states[user_id]["step"] = "asking_date"
            response_text = f"Got it: {service_val}. 🗓️ \n\nWhat date would you like? (Format: YYYY-MM-DD, or just say 'tomorrow')"
        else:
            response_text = "I didn't quite catch that. 🤔 \n\nPlease specify: 'Medical Consultation' or 'Medical Clearance'."

    # ==================================================
    # asking date
    # ==================================================
    elif step == "asking_date":
        chosen_date = None
        if "tomorrow" in message:
            chosen_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            match = re.search(r'\d{4}-\d{2}-\d{2}', message)
            if match:
                chosen_date = match.group(0)
        
        if chosen_date:
            chat_states[user_id]["data"]["appointment_date"] = chosen_date
            chat_states[user_id]["step"] = "asking_time"
            response_text = f"Date set to {chosen_date}. ✅ \n\nWhat time works best? (Format: HH:MM, e.g., 09:30 or 14:00)"
        else:
            response_text = "Oops, that looks like an invalid date. 📅 \n\nPlease use YYYY-MM-DD (e.g., 2025-10-25) or just say 'tomorrow'."

    # ==================================================
    # asking time
    # ==================================================
    elif step == "asking_time":
        match = re.search(r'\d{1,2}:\d{2}', message)
        if match:
            time_val = match.group(0)
            if len(time_val) == 4:
                time_val = "0" + time_val
            formatted_time = time_val + ":00"
            
            chat_states[user_id]["data"]["appointment_time"] = formatted_time
            chat_states[user_id]["step"] = "asking_urgency"
            response_text = "Time recorded. 🕒 \n\nIs this 'Normal' or 'Urgent'?"
        else:
            response_text = "Please enter a valid time in HH:MM format (24-hour clock, e.g., 14:00)."

    # ==================================================
    # asking urgency
    # ==================================================
    elif step == "asking_urgency":
        valid_urgencies = ["normal", "urgent"]
        found = next((u for u in valid_urgencies if u in message), None)
        
        if found:
            db_urgency = "Urgent" if found == "urgent" else "Normal"
            
            chat_states[user_id]["data"]["urgency"] = db_urgency
            chat_states[user_id]["step"] = "asking_reason"
            response_text = "Understood. 📝 \n\nFinally, please briefly describe the reason for your visit."
        else:
            response_text = "Please choose a valid urgency: 'Normal' or 'Urgent'."

    # ==================================================
    # asking reason then save to DB
    # ==================================================
    elif step == "asking_reason":
        chat_states[user_id]["data"]["reason"] = chat.message 
        
        data = chat_states[user_id]["data"]
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO appointments (student_id, appointment_date, appointment_time, service_type, urgency, reason, booking_mode, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'ai_chatbot', 'pending')
            """, (
                user_id, 
                data['appointment_date'], 
                data['appointment_time'], 
                data['service_type'], 
                data['urgency'], 
                data['reason']
            ))
            conn.commit()
            
            # happy responses
            response_text = (
                "🎉 Hooray! Your appointment has been successfully booked! \n\n"
                "I've saved it to your dashboard. We look forward to seeing you! 💙 \n\n"
                "Is there anything else I can help you with?"
            )
            
        except Error as e:
            response_text = f"❌ Oh no! There was an error saving your appointment: {str(e)}. Please try again later."
        finally:
            cursor.close()
            conn.close()
            
        # reset state to idle so they can say "Thanks" or book again
        chat_states[user_id] = {"step": "idle", "data": {}}

    return {"response": response_text, "requires_action": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)