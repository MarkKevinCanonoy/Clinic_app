const API_URL = 'http://localhost:8000/api';
let allAppointments = [];

// --- Chat history memory ---
let chatHistory = []; 

// 1. Check login
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');

if (!token || role !== 'student') {
    window.location.href = 'index.html';
}

// 2. Display info
document.getElementById('user-name').textContent = localStorage.getItem('fullName');

// 3. Date constraint
const dateInput = document.getElementById('book-date'); 
if(dateInput) {
    dateInput.min = new Date().toISOString().split('T')[0];
}

// 4. Tabs
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(`${tabName}-tab`).classList.add('active');
    event.currentTarget.classList.add('active'); 
    
    if (tabName === 'appointments') loadAppointments();
    if (tabName === 'chatbot') initChatbot();
}

// 5. Logout
function logout() {
    localStorage.clear();
    window.location.href = 'index.html';
}

// --- Booking Logic ---
async function handleBooking(e) {
    e.preventDefault(); 
    const form = document.getElementById('booking-form');
    const serviceType = document.getElementById('book-type').value;
    const date = document.getElementById('book-date').value;
    const timeRaw = document.getElementById('book-time').value;
    const urgency = document.getElementById('book-urgency').value;
    const reason = document.getElementById('book-reason').value;

    if(!serviceType || !date || !timeRaw || !reason) {
        alert("Please fill in all fields.");
        return;
    }

    const time = timeRaw.length === 5 ? timeRaw + ":00" : timeRaw;

    try {
        const response = await fetch(`${API_URL}/appointments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({
                appointment_date: date,
                appointment_time: time,
                service_type: serviceType,
                urgency: urgency,
                reason: reason,
                booking_mode: 'standard'
            })
        });

        const data = await response.json();
        if (!response.ok) { alert(data.detail || 'Booking failed'); return; }

        alert("Appointment booked successfully!");
        form.reset();
        loadAppointments(); 
    } catch (error) {
        console.error('Booking error:', error);
        alert('Connection error.');
    }
}

// --- Appointment List Logic (FIXED) ---
async function loadAppointments() {
    const container = document.getElementById('appointments-list');
    container.innerHTML = '<p>Loading...</p>';

    try {
        const response = await fetch(`${API_URL}/appointments`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        allAppointments = await response.json();
        displayAppointments(allAppointments);
        
    } catch (error) {
        console.error('Error:', error);
        container.innerHTML = '<p>Error loading appointments.</p>';
    }
}

function displayAppointments(appointments) {
    const container = document.getElementById('appointments-list');
    
    if (!appointments || appointments.length === 0) {
        container.innerHTML = '<p>No appointments found.</p>';
        return;
    }
    
    container.innerHTML = appointments.map(apt => {
        const niceDate = new Date(apt.appointment_date).toDateString();
        
        // Capitalize status (e.g. "pending" -> "Pending")
        const statusLabel = apt.status.charAt(0).toUpperCase() + apt.status.slice(1);

        // --- NEW: Admin Note Logic ---
        // If rejected AND has a note, show the red box
        let adminNoteHtml = '';
        if (apt.status === 'rejected' && apt.admin_note) {
            adminNoteHtml = `
                <div class="admin-note-box">
                    <i class="fas fa-exclamation-circle"></i> 
                    <strong>Reason for Rejection:</strong><br> 
                    ${apt.admin_note}
                </div>
            `;
        }

        let actionBtn = '';
        if (apt.status === 'pending') {
            actionBtn = `<button onclick="cancelAppointment(${apt.id})" class="btn-cancel">Cancel Request</button>`;
        } else {
            actionBtn = `<button onclick="deleteHistory(${apt.id})" class="btn-cancel" style="background:#ffcdd2; color:#c62828;">Delete History</button>`;
        }

        return `
        <div class="appointment-card status-${apt.status}">
            <div class="apt-header">
                <span class="apt-date">${niceDate}</span>
                <span class="status-pill ${apt.status}">${statusLabel}</span>
            </div>
            <div class="apt-body">
                <p><strong>Time:</strong> ${apt.appointment_time}</p>
                <p><strong>Service:</strong> ${apt.service_type || 'General'}</p>
                <p><strong>Reason:</strong> ${apt.reason}</p>
                
                ${adminNoteHtml} 
            </div>
            <div class="apt-actions">
                ${actionBtn}
            </div>
        </div>
        `;
    }).join('');
}

async function cancelAppointment(id) {
    if (!confirm('Cancel this appointment?')) return;
    await deleteOrCancel(id);
}

async function deleteHistory(id) {
    if (!confirm('Remove this record from history?')) return;
    await deleteOrCancel(id);
}

async function deleteOrCancel(id) {
    try {
        const response = await fetch(`${API_URL}/appointments/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            alert("Success");
            loadAppointments();
        } else {
            alert("Failed to update.");
        }
    } catch (error) {
        console.error(error);
    }
}


// --- Chatbot Logic ---

function initChatbot() {
    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages && chatMessages.children.length === 0) {
        addChatMessage('bot', "Hello! I can help you book an appointment. Just tell me when you want to come.");
    }
}

function addChatMessage(sender, message) {
    const chatMessages = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `chat-message ${sender}`;
    div.textContent = message;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    
    addChatMessage('user', message);
    input.value = ''; 
    
    try {
        const payload = {
            message: message,
            history: chatHistory
        };

        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        addChatMessage('bot', data.response);

        chatHistory.push({ "role": "user", "parts": [message] });
        chatHistory.push({ "role": "model", "parts": [data.response] });

    } catch (error) {
        console.error('Chat error:', error);
        addChatMessage('bot', 'Sorry, I lost connection to the server.');
    }
}

const chatInput = document.getElementById('chat-input');
if(chatInput) {
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });
}