import requests
import json

try:
    response = requests.get("http://localhost:8000/api/users")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")