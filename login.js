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

            // success animation (toast)
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
                // redirect based on role
                if (data.role === "student") {
                    window.location.href = "student-dashboard.html";
                } else if (data.role === "admin" || data.role === "super_admin") {
                    window.location.href = "admin-dashboard.html";
                }
            });

        } else {
            // --- FIX IS HERE ---
            let errorText = 'Invalid email or password.';

            // if status is 422, it means the input format is wrong (e.g. bad email)
            if (response.status === 422) {
                errorText = "Please enter a valid email address format.";
            } 
            // otherwise, use the server message if it's a simple string
            else if (data.detail && typeof data.detail === 'string') {
                errorText = data.detail;
            }

            Swal.fire({
                icon: 'error',
                title: 'Login Failed',
                text: errorText,
                confirmButtonColor: '#e74c3c'
            });
        }
    } catch (error) {
        console.error(error);
        Swal.fire({
            icon: 'error',
            title: 'Server Error',
            text: 'Cannot connect to the server.',
            confirmButtonColor: '#e74c3c'
        });
    }
});