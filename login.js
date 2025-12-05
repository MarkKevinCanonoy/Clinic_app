const API_URL = 'http://localhost:8000/api';

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('error-message');
    
    try {
        const response = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, password })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            errorMessage.textContent = data.detail || 'Login failed';
            errorMessage.style.color = 'red';
            return;
        }
        
        // to store token and user info
        localStorage.setItem('token', data.token);
        localStorage.setItem('role', data.role);
        localStorage.setItem('userId', data.user_id);
        localStorage.setItem('fullName', data.full_name);
        
        // redirect based on role
        if (data.role === 'student') {
            window.location.href = 'student-dashboard.html';
        } else if (data.role === 'admin' || data.role === 'super_admin') {
            window.location.href = 'admin-dashboard.html';
        }
        
    } catch (error) {
        errorMessage.textContent = 'Connection error. Please try again.';
        errorMessage.style.color = 'red';
        console.error('Login error:', error);
    }
});