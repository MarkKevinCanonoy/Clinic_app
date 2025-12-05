const API_URL = 'http://localhost:8000/api';

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const fullName = document.getElementById('full-name').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm-password').value;
    const messageDiv = document.getElementById('message');
    
    // validate passwords match
    if (password !== confirmPassword) {
        messageDiv.textContent = 'Passwords do not match';
        messageDiv.style.color = 'red';
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                full_name: fullName,
                email: email,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            messageDiv.textContent = data.detail || 'Registration failed';
            messageDiv.style.color = 'red';
            return;
        }
        
        messageDiv.textContent = 'Registration successful! Redirecting to login...';
        messageDiv.style.color = 'green';
        
        setTimeout(() => {
            window.location.href = 'index.html';
        }, 2000);
        
    } catch (error) {
        messageDiv.textContent = 'Connection error. Please try again.';
        messageDiv.style.color = 'red';
        console.error('Registration error:', error);
    }
});