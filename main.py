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


def create_default_users():
    """
    creates default Super Admin and Admin if they don't exist.
    runs automatically when the server starts.
    """
    print("Checking for default admin accounts...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        default_users = [
            {
                "full_name": "Super Admin",
                "email": "superadmin@clinic.com",
                "password": "admin123", 
                "role": "super_admin"
            },
            {
                "full_name": "Clinic Admin",
                "email": "admin@clinic.com",
                "password": "admin123", 
                "role": "admin"
            }
        ]

        for user in default_users:
            # check if user already exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (user['email'],))
            existing_user = cursor.fetchone()

            if not existing_user:
                # hash the password using your existing helper function
                hashed_pw = hash_password(user['password'])
                
                cursor.execute(
                    "INSERT INTO users (full_name, email, password, role) VALUES (%s, %s, %s, %s)",
                    (user['full_name'], user['email'], hashed_pw, user['role'])
                )
                print(f"Created default user: {user['email']} ({user['role']})")
            else:
                print(f"User {user['email']} already exists. Skipping.")

        conn.commit()
    except Error as e:
        print(f"Error seeding database: {e}")
    finally:
        cursor.close()
        conn.close()




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

# JWT conf
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
security = HTTPBearer()

# database configuration
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

# --- pydantic ---
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

# --- helper ---
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

# logic to handle deletion vs cancellation
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

        # permission check
        if current_user['role'] == 'student' and appt['student_id'] != current_user['user_id']:
            raise HTTPException(status_code=403, detail="Not authorized")

        # logic: if mag 'pending', e CANCEL. if 'finished'/'rejected'/'canceled', e DELETE.
        if appt['status'] == 'pending':
             cursor.execute("UPDATE appointments SET status = 'canceled', updated_at = NOW() WHERE id = %s", (appointment_id,))
             message = "Appointment canceled successfully"
        else:
             # hard delete
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

@app.post("/api/chat")
async def chat_booking(chat: ChatMessage, current_user = Depends(get_current_user)):
    return {
        "response": "I'll help you book an appointment. Please provide the date, time, and reason for your visit.",
        "requires_action": False
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)