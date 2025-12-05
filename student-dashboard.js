const API_URL = 'http://localhost:8000/api';
let allAppointments = [];

// check auth
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');
if (!token || role !== 'student') {
    window.location.href = 'index.html';
}

// display user name
document.getElementById('user-name').textContent = localStorage.getItem('fullName');

// set minimum date to today
const dateInput = document.getElementById('book-date'); 
if(dateInput) {
    dateInput.min = new Date().toISOString().split('T')[0];
}

// tab switching
function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    
    document.getElementById(`${tabName}-tab`).classList.add('active');
    event.currentTarget.classList.add('active'); 
    
    if (tabName === 'appointments') {
        loadAppointments();
    } else if (tabName === 'chatbot') {
        initChatbot();
    }
}

function logout() {
    localStorage.clear();
    window.location.href = 'index.html';
}

async function handleBooking(e) {
    e.preventDefault(); 
    
    const form = document.getElementById('booking-form');

    // getting values
    const serviceType = document.getElementById('book-type').value;
    const date = document.getElementById('book-date').value;
    const timeRaw = document.getElementById('book-time').value;
    const urgency = document.getElementById('book-urgency').value;
    const reason = document.getElementById('book-reason').value;

    // validate
    if(!serviceType || !date || !timeRaw || !reason || !urgency) {
        alert("Please fill in all required fields.");
        return;
    }

    const time = timeRaw + ":00"; 

    try {
        // try sending to API
        const response = await fetch(`${API_URL}/appointments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
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

        if (!response.ok) {
            alert(data.detail || 'Booking failed');
            return;
        }

        alert("Appointment booked successfully!");
        form.reset();
        
        // refresh the appointments list
        await loadAppointments();
        
            // switch to appointments tab
        const tabs = document.querySelectorAll('.tab-btn');
        if(tabs[2]) tabs[2].click(); 

    } catch (error) {
        console.error('Booking error:', error);
        alert('Connection error. Please try again.');
    }
}

// load appointments
async function loadAppointments() {
    try {
        const response = await fetch(`${API_URL}/appointments`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        allAppointments = await response.json();
        displayAppointments(allAppointments);
        
    } catch (error) {
        console.error('Error loading appointments:', error);
        document.getElementById('appointments-list').innerHTML = '<p>Error loading appointments</p>';
    }
}

function displayAppointments(appointments) {
    const container = document.getElementById('appointments-list');
    
    if (!appointments || appointments.length === 0) {
        container.innerHTML = '<p>No appointments found</p>';
        return;
    }
    
    container.innerHTML = appointments.map(apt => {
        // logic: if status is pending, show Cancel. if finished/rejected/canceled, show Delete.
        let actionButton = '';
        
        if (apt.status === 'pending') {
            actionButton = `<button onclick="cancelAppointment(${apt.id})" class="btn-cancel">Cancel Request</button>`;
        } else {
            actionButton = `<button onclick="deleteHistory(${apt.id})" class="btn-cancel" style="background-color: #ffcdd2; color: #c62828; border: 1px solid #ef9a9a;">Delete Appointment</button>`;
        }

        return `
        <div class="appointment-card status-${apt.status}">
            <div class="apt-header">
                <span class="apt-date">${formatDate(apt.appointment_date)}</span>
                <span class="apt-time">${formatTime(apt.appointment_time)}</span>
            </div>
            <div class="apt-body">
                <p><strong>Service:</strong> ${apt.service_type || 'General'}</p>
                <p><strong>Urgency:</strong> ${apt.urgency || 'Low'}</p>
                <p><strong>Reason:</strong> ${apt.reason}</p>
                <p><strong>Status:</strong> <span class="status-badge">${apt.status.toUpperCase()}</span></p>
                <p><strong>Booking Mode:</strong> ${apt.booking_mode === 'ai_chatbot' ? 'AI Chatbot' : 'Standard'}</p>
                ${apt.admin_note ? `<p><strong>Note:</strong> ${apt.admin_note}</p>` : ''}
            </div>
            <div class="apt-actions">
                ${actionButton}
            </div>
        </div>
    `}).join('');
}

async function deleteHistory(id) {
    if (!confirm('Remove this appointment?')) return;
    
    try {
        const response = await fetch(`${API_URL}/appointments/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            alert('Appointment removed.');
            loadAppointments();
        } else {
            alert('Failed to remove.');
        }
    } catch (error) {
        console.error(error);
    }
}

async function cancelAppointment(id) {
    if (!confirm('Are you sure you want to cancel this appointment?')) return;
    try {
        const response = await fetch(`${API_URL}/appointments/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            alert('Appointment canceled successfully');
            loadAppointments();
        } 
    } catch (error) { console.error(error); }
}

function filterAppointments() {
    const filter = document.getElementById('status-filter').value;
    
    if (filter === 'all') {
        displayAppointments(allAppointments);
    } else {
        const filtered = allAppointments.filter(apt => apt.status === filter);
        displayAppointments(filtered);
    }
}

async function cancelAppointment(id) {
    if (!confirm('Are you sure you want to cancel this appointment?')) return;
    
    try {
        const response = await fetch(`${API_URL}/appointments/${id}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            alert('Appointment canceled successfully');
            loadAppointments();
        } else {
            alert('Failed to cancel appointment');
        }
        
    } catch (error) {
        console.error('Error canceling appointment:', error);
        alert('Failed to cancel appointment');
    }
}

function initChatbot() {
    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages && chatMessages.children.length === 0) {
        addChatMessage('bot', 'Hello! I\'m here to help you book an appointment. Please tell me when you\'d like to visit the clinic and what\'s the reason for your visit.');
    }
}

function addChatMessage(sender, message) {
    const chatMessages = document.getElementById('chat-messages');
    if(!chatMessages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}`;
    messageDiv.textContent = message;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    addChatMessage('user', message);
    input.value = '';
    
    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        addChatMessage('bot', data.response);
        
    } catch (error) {
        console.error('Chat error:', error);
        addChatMessage('bot', 'Sorry, I encountered an error. Please try again.');
    }
}

const chatInput = document.getElementById('chat-input');
if(chatInput) {
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendChatMessage();
        }
    });
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function formatTime(timeStr) {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
}

loadAppointments();