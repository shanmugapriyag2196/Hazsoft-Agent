import httpx

response = httpx.get("http://localhost:8000/api/users")
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")