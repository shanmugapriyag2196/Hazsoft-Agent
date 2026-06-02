import httpx
import json

# Test data
test_user = {
    "fullName": "Test User",
    "email": "test@example.com",
    "role": "User",
    "status": "Active",
    "password": "temp123"
}

try:
    response = httpx.post(
        "http://localhost:8000/api/users",
        json=test_user,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")