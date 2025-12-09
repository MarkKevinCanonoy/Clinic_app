const API_URL = "http://localhost:8000/api";

document.getElementById("login-form").addEventListener("submit", async function(event) {
    event.preventDefault();

    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    try {
        const response = await fetch(`${API_URL}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });

        const data = await response.json();

        if (response.ok) {
            localStorage.setItem("token", data.token);
            localStorage.setItem("role", data.role);
            localStorage.setItem("user_id", data.user_id);
            localStorage.setItem("full_name", data.full_name || "User"); 

            // Success Animation (Toast)
            const Toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 1500,
                timerProgressBar: true,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer)
                    toast.addEventListener('mouseleave', Swal.resumeTimer)
                }
            });

            Toast.fire({
                icon: 'success',
                title: 'Signed in successfully'
            }).then(() => {
                // Redirect based on role
                if (data.role === "student") {
                    window.location.href = "student-dashboard.html";
                } else if (data.role === "admin" || data.role === "super_admin") {
                    window.location.href = "admin-dashboard.html";
                }
            });

        } else {
            // Invalid Credentials Alert
            Swal.fire({
                icon: 'error',
                title: 'Login Failed',
                text: data.detail || 'Invalid email or password.',
                confirmButtonColor: '#e74c3c'
            });
        }
    } catch (error) {
        Swal.fire({
            icon: 'error',
            title: 'Server Error',
            text: 'Cannot connect to the server.',
            confirmButtonColor: '#e74c3c'
        });
    }
});