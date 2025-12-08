from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
import bcrypt
import jwt
import os
import json 
import google.generativeai as genai
from dotenv import load_dotenv # this loads the .env file

# --- configuration setup ---

# 1. load the variables from .env file
load_dotenv()

# 2. get keys safely
API_KEY = os.getenv("GOOGLE_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")

# 3. configure google ai
if not API_KEY:
    print("warning: google_api_key not found in .env file")
else:
    genai.configure(api_key=API_KEY)
    # use the flash model because it is fast and free
    # changed to latest to fix limit errors
    model = genai.GenerativeModel('gemini-flash-latest')

# 4. database config
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'kurt_cobain', 
    'database': 'school_clinic'
}

# --- database helper ---
def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        raise HTTPException(status_code=500, detail=f"database connection failed: {str(e)}")

# --- helper functions ---
def create_default_users():
    """
    creates default admin accounts if they do not exist.
    """
    print("checking for default admin accounts...")
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
                print(f"created default user: {user['email']}")
        conn.commit()
    except Error as e:
        print(f"error seeding database: {e}")
    finally:
        cursor.close()
        conn.close()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: int, role: str, full_name: str) -> str:
    payload = {
        'user_id': user_id,
        'role': role,
        'full_name': full_name,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")

security = HTTPBearer()
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    return decode_token(token)

# --- pydantic models ---
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

# updated chat model to include history
class ChatMessage(BaseModel):
    message: str
    # history is a list of previous messages (optional)
    history: List[dict] = []

# --- main app ---
app = FastAPI()

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

# --- api routes ---

@app.post("/api/register")
def register(user: UserRegister):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="email already registered")
        
        hashed_pw = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, 'student')",
            (user.full_name, user.email, hashed_pw)
        )
        conn.commit()
        return {"message": "registration successful"}
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
            raise HTTPException(status_code=401, detail="invalid email or password")
        
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
        raise HTTPException(status_code=403, detail="only students can book appointments")
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO appointments (student_id, appointment_date, appointment_time, service_type, urgency, reason, booking_mode, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            current_user['user_id'], appointment.appointment_date, appointment.appointment_time, 
            appointment.service_type, appointment.urgency, appointment.reason, appointment.booking_mode
        ))
        conn.commit()
        return {"message": "appointment booked successfully", "id": cursor.lastrowid}
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

# --- ADMIN USER MANAGEMENT (THESE WERE MISSING) ---

# 1. Get all users
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

# 2. Delete a user (This was the main one missing)
@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current_user = Depends(get_current_user)):
    # check permission
    if current_user['role'] != 'super_admin':
        raise HTTPException(status_code=403, detail="Only Super Admins can delete users")
    
    # prevent deleting yourself
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

# 3. Create a new admin (This was also missing)
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

# --------------------------------------------------

@app.delete("/api/appointments/{appointment_id}")
def delete_or_cancel_appointment(appointment_id: int, current_user = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # get current status and owner
        cursor.execute("SELECT student_id, status FROM appointments WHERE id = %s", (appointment_id,))
        appt = cursor.fetchone()
        
        if not appt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # FIX: ADMIN POWER -> Admins always HARD DELETE
        if current_user['role'] in ['admin', 'super_admin']:
             cursor.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
             message = "Appointment permanently deleted."
        
        # STUDENT LOGIC -> Verify ownership first
        elif current_user['role'] == 'student':
            if appt['student_id'] != current_user['user_id']:
                raise HTTPException(status_code=403, detail="Not authorized")

            # If pending, just Cancel it. If finished/canceled, Delete it.
            if appt['status'] == 'pending':
                cursor.execute("UPDATE appointments SET status = 'canceled', updated_at = NOW() WHERE id = %s", (appointment_id,))
                message = "Appointment canceled successfully."
            else:
                cursor.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
                message = "History record deleted successfully."
        
        else:
             raise HTTPException(status_code=403, detail="Action not allowed")

        conn.commit()
        return {"message": message}
    finally:
        cursor.close()
        conn.close()

# --- the smart ai chat logic ---
@app.post("/api/chat")
async def chat_booking(chat: ChatMessage, current_user = Depends(get_current_user)):
    """
    Handles AI Chat.
    """
    conn = get_db()
    cursor = conn.cursor(dictionary=True) # dictionary cursor to access data by name

    # --- STEP 1: GET CURRENT APPOINTMENTS ---
    # fetch the student's active appointments so the AI knows about them.
    try:
        cursor.execute("""
            SELECT id, appointment_date, appointment_time, reason 
            FROM appointments 
            WHERE student_id = %s AND status IN ('pending', 'approved')
            ORDER BY appointment_date ASC
        """, (current_user['user_id'],))
        active_appts = cursor.fetchall()
        
        # turn the database list into a simple text string for the AI
        appt_list_text = ""
        if active_appts:
            for appt in active_appts:
                appt_list_text += f"- ID {appt['id']}: {appt['appointment_date']} at {appt['appointment_time']} (Reason: {appt['reason']})\n"
        else:
            appt_list_text = "None."
            
    finally:
        cursor.close()
        conn.close()

    # --- STEP 2: SMART INSTRUCTIONS ---
    system_instruction = f"""
    ROLE: You are a fast, efficient, and happy School Clinic receptionist. 😊
    Student: {current_user['full_name']}
    Today: {datetime.now().strftime("%Y-%m-%d")}

    CONTEXT (The student's current appointments):
    {appt_list_text}

    YOUR RULES:
    1. **Keep it Short:** maximum 2 sentences. Be direct.
    2. **Booking:** Ask for Date, Time, Reason, Service Type.
    3. **Canceling:** If they want to cancel, look at the "CONTEXT" list above.
       - If they say "Cancel tomorrow", find the ID for tomorrow and output the JSON.
       - If you are not sure which one, list them and ask "Which ID?".

    🔴 ACTIONS (Output JSON only):

    [ACTION 1: BOOKING] - When you have all 4 details:
    {{
      "action": "book_appointment",
      "date": "YYYY-MM-DD",
      "time": "HH:MM:00",
      "reason": "short reason",
      "service_type": "Medical Consultation", 
      "urgency": "Normal"
    }}

    [ACTION 2: CANCELING] - When user confirms which one to remove:
    {{
      "action": "cancel_appointment",
      "appointment_id": 123
    }}
    """

    try:
        # --- STEP 3: TALK TO AI ---
        chat_session = model.start_chat(
            history=[
                {"role": "user", "parts": [system_instruction]},
                {"role": "model", "parts": ["Got it! I see the schedule. I will keep answers short. 😊"]}
            ]
        )

        for msg in chat.history:
            chat_session.history.append(msg)

        response = chat_session.send_message(chat.message)
        ai_text = response.text

        # --- STEP 4: CHECK FOR JSON ACTIONS ---
        if "{" in ai_text and "}" in ai_text:
            try:
                # xxtract JSON
                start = ai_text.find('{')
                end = ai_text.rfind('}') + 1
                data = json.loads(ai_text[start:end])

                # ACTION A: BOOKING
                if data.get("action") == "book_appointment":
                    conn = get_db()
                    cursor = conn.cursor(buffered=True)
                    
                    # duplicate check
                    cursor.execute("""
                        SELECT id FROM appointments 
                        WHERE student_id = %s AND appointment_date = %s AND appointment_time = %s
                    """, (current_user['user_id'], data['date'], data['time']))
                    
                    if cursor.fetchone():
                        cursor.close()
                        conn.close()
                        return {"response": "You already have a booking at that time! 😊", "requires_action": False}

                    cursor.execute("""
                        INSERT INTO appointments (student_id, appointment_date, appointment_time, service_type, urgency, reason, booking_mode, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'ai_chatbot', 'pending')
                    """, (current_user['user_id'], data['date'], data['time'], data['service_type'], data['urgency'], data['reason']))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    return {"response": f"Booked for {data['date']} at {data['time']}! ✅", "requires_action": False}

                # ACTION B: CANCELING
                elif data.get("action") == "cancel_appointment":
                    appt_id = data.get("appointment_id")
                    
                    conn = get_db()
                    cursor = conn.cursor()
                    
                    # verify this appointment belongs to the user before deleting
                    cursor.execute("SELECT id FROM appointments WHERE id = %s AND student_id = %s", (appt_id, current_user['user_id']))
                    
                    if cursor.fetchone():
                        cursor.execute("UPDATE appointments SET status = 'canceled' WHERE id = %s", (appt_id,))
                        conn.commit()
                        msg = f"Okay, appointment #{appt_id} has been canceled. 🗑️"
                    else:
                        msg = "I couldn't find that appointment in your list. 🤔"
                        
                    cursor.close()
                    conn.close()
                    return {"response": msg, "requires_action": False}

            except Exception as e:
                print(f"JSON Error: {e}")
                return {"response": "I had a small error. Please try again.", "requires_action": False}

        # Normal Reply
        return {"response": ai_text, "requires_action": False}

    except Exception as e:
        print(f"AI Error: {e}")
        return {"response": "System is offline briefly. Try again.", "requires_action": False}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)