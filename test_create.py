import requests
import json

# Test creating a user
user_data = {
    "fullName": "Test User 2",
    "email": "test2@example.com",
    "role": "Admin",
    "status": "Active",
    "password": "temp123"
}

try:
    response = requests.post(
        "http://localhost:8000/api/users",
        json=user_data,
        headers={"Content-Type": "application/json"}
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")