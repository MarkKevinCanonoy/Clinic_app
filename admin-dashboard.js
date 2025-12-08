const API_URL = 'http://localhost:8000/api';
let allAppointments = [];
let currentAppointmentId = null;

// authentication check
const token = localStorage.getItem('token');
const role = localStorage.getItem('role');
const fullName = localStorage.getItem('full_name') || 'Admin';

if (!token || (role !== 'admin' && role !== 'super_admin')) {
    alert("Unauthorized access. Redirecting to login.");
    window.location.href = 'index.html';
}

document.getElementById('user-name').textContent = fullName;
document.getElementById('user-role').textContent = role === 'super_admin' ? 'Super Admin' : 'Admin';

document.addEventListener('DOMContentLoaded', () => {
    loadAppointments();
    if(role === 'super_admin') {
        loadUsers();
    } else {
        const userTabBtn = document.getElementById('manage-users-tab');
        if(userTabBtn) userTabBtn.style.display = 'none';
    }
});

function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabName + '-tab').style.display = 'block';
    event.currentTarget.classList.add('active');
    
    if (tabName === 'appointments') loadAppointments();
    if (tabName === 'users') loadUsers();
}

function logout() {
    if(confirm("Logout?")) {
        localStorage.clear();
        window.location.href = 'index.html';
    }
}

// --- Appointment Logic ---

async function loadAppointments() {
    try {
        const response = await fetch(`${API_URL}/appointments`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Failed to fetch");
        allAppointments = await response.json();
        applyFiltersAndSort(); 
    } catch (error) {
        console.error(error);
        document.getElementById('appointments-list').innerHTML = `<tr><td colspan="6" style="text-align:center; color:red;">Error loading data.</td></tr>`;
    }
}

function applyFiltersAndSort() {
    const statusFilter = document.getElementById('status-filter').value;
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const sortChoice = document.getElementById('sort-order').value;

    let filtered = allAppointments.filter(apt => {
        const matchesStatus = statusFilter === 'all' || apt.status === statusFilter;
        const matchesSearch = apt.student_name.toLowerCase().includes(searchTerm);
        
        let matchesType = true;
        const service = (apt.service_type || '').toLowerCase();
        const urgency = (apt.urgency || '').toLowerCase();

        if (sortChoice === 'clearance-urgent') {
            matchesType = service.includes('clearance') && (urgency === 'urgent' || urgency === 'high');
        } else if (sortChoice === 'consultation-urgent') {
            matchesType = service.includes('consultation') && (urgency === 'urgent' || urgency === 'high');
        } else if (sortChoice === 'clearance-normal') {
            matchesType = service.includes('clearance') && (urgency === 'normal' || urgency === 'low');
        } else if (sortChoice === 'consultation-normal') {
            matchesType = service.includes('consultation') && (urgency === 'normal' || urgency === 'low');
        }

        return matchesStatus && matchesSearch && matchesType;
    });

    filtered.sort((a, b) => new Date(b.appointment_date) - new Date(a.appointment_date));
    displayAppointments(filtered);
}

function displayAppointments(data) {
    const tbody = document.getElementById('appointments-list');
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 20px;">No appointments found matching these criteria.</td></tr>`;
        return;
    }

    data.forEach(apt => {
        const urgency = apt.urgency || 'Low';
        const urgencyClass = (urgency.toLowerCase() === 'urgent' || urgency.toLowerCase() === 'high') ? 'color: var(--danger); font-weight:bold;' : 'color: var(--success);';
        
        // Capitalize status
        const statusLabel = apt.status.charAt(0).toUpperCase() + apt.status.slice(1);

        // Admins can delete ANY appointment now
        const showDelete = true; 

        const row = `
            <tr>
                <td>${formatDate(apt.appointment_date)}<br><small>${formatTime(apt.appointment_time)}</small></td>
                <td>
                    <span style="font-weight:bold">${apt.student_name}</span><br>
                    <small style="color:#666">${apt.student_email || ''}</small>
                </td>
                <td>${apt.service_type || 'General'}</td>
                <td><span style="${urgencyClass}">${urgency}</span></td>
                <td><span class="status-pill ${apt.status}">${statusLabel}</span></td>
                
                <td>
                    <div class="action-buttons">
                        <button class="btn-primary" style="padding: 5px 10px; font-size: 0.8rem;" onclick="openAppointmentModal(${apt.id})">View</button>
                        ${showDelete ? `<button class="btn-delete" onclick="deleteAppointment(${apt.id})"><i class="fas fa-trash"></i></button>` : ''}
                    </div>
                </td>
            </tr>
        `;
        tbody.insertAdjacentHTML('beforeend', row);
    });
}

async function deleteAppointment(id) {
    if(!confirm("Are you sure you want to permanently delete this record?")) return;
    try {
        const response = await fetch(`${API_URL}/appointments/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if(response.ok) {
            alert("Record deleted.");
            loadAppointments();
        } else {
            alert("Failed to delete.");
        }
    } catch(e) { console.error(e); }
}

function formatDate(d) {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
function formatTime(t) {
    const [h, m] = t.split(':');
    const d = new Date(); d.setHours(h, m);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function openAppointmentModal(id) {
    const apt = allAppointments.find(a => a.id === id);
    if(!apt) return;
    currentAppointmentId = id;
    const details = document.getElementById('appointment-details');
    details.innerHTML = `
        <p><strong>Student:</strong> ${apt.student_name}</p>
        <p><strong>Service:</strong> ${apt.service_type}</p>
        <p><strong>Urgency:</strong> ${apt.urgency}</p>
        <p><strong>Reason:</strong> ${apt.reason}</p>
        <hr style="margin: 10px 0; border: 0; border-top: 1px solid #eee;">
        ${apt.admin_note ? `<div class="admin-note-box"><strong>Current Note:</strong> ${apt.admin_note}</div>` : ''}
    `;
    document.getElementById('reject-form').style.display = 'none';
    document.getElementById('appointment-modal').style.display = 'flex';
}
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function showRejectForm() { document.getElementById('reject-form').style.display = 'block'; }

async function updateAppointmentStatus(status) {
    const note = document.getElementById('admin-note').value;
    await fetch(`${API_URL}/appointments/${currentAppointmentId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ status: status, admin_note: note })
    });
    closeModal('appointment-modal');
    loadAppointments();
}

// --- User Management Logic (Updated for Filters) ---

async function loadUsers() {
    try {
        const response = await fetch(`${API_URL}/users`, { headers: { 'Authorization': `Bearer ${token}` } });
        let users = await response.json();
        
        // 1. Filter Logic
        const filter = document.getElementById('user-role-filter').value;
        if (filter === 'student') {
            users = users.filter(u => u.role === 'student');
        } else if (filter === 'admin') {
            users = users.filter(u => u.role === 'admin' || u.role === 'super_admin');
        }

        const tbody = document.getElementById('users-list');
        tbody.innerHTML = '';
        
        if (users.length === 0) {
             tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 20px;">No users found.</td></tr>`;
             return;
        }

        users.forEach(u => {
            // Colors
            let roleColor = '#333';
            let roleLabel = 'Student';

            if (u.role === 'student') {
                roleColor = 'green';
                roleLabel = 'Student';
            } else if (u.role === 'super_admin') {
                roleColor = 'purple';
                roleLabel = 'Super Admin';
            } else {
                roleColor = 'blue';
                roleLabel = 'Admin';
            }

            tbody.insertAdjacentHTML('beforeend', `
                <tr>
                    <td>${u.full_name}</td>
                    <td>${u.email}</td>
                    <td><span style="color: ${roleColor}; font-weight:bold;">${roleLabel}</span></td>
                    <td>${new Date(u.created_at).toLocaleDateString()}</td>
                    <td><button onclick="deleteUser(${u.id})" class="btn-delete"><i class="fas fa-trash"></i></button></td>
                </tr>
            `);
        });
    } catch (e) { console.error(e); }
}

async function deleteUser(id) {
    if(!confirm("Delete this user?")) return;
    await fetch(`${API_URL}/users/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
    loadUsers();
}

function showAddUserModal() { document.getElementById('add-user-modal').style.display = 'flex'; }

async function handleNewUser(e) {
    e.preventDefault();
    const body = {
        full_name: document.getElementById('new-full-name').value,
        email: document.getElementById('new-email').value,
        password: document.getElementById('new-password').value,
        role: document.getElementById('new-role').value
    };
    const res = await fetch(`${API_URL}/admin/create-user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(body)
    });
    if(res.ok) { alert("User Created"); closeModal('add-user-modal'); loadUsers(); }
    else { alert("Failed"); }
}