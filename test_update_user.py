import httpx
import json

# First get a user to update
response = httpx.get("http://localhost:8000/api/users")
if response.status_code == 200:
    users = response.json()
    if users:
        # Take the first user for testing
        user_id = users[0]["id"]
        print(f"Testing update for user ID: {user_id}")
        
        # Update data
        update_data = {
            "fullName": "Updated User",
            "email": "updated@example.com",
            "role": "Admin",
            "status": "Active",
            "password": "updated123"
        }
        
        # Try to update the user
        update_response = httpx.put(
            f"http://localhost:8000/api/users/{user_id}",
            json=update_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"Update Status: {update_response.status_code}")
        print(f"Update Response: {update_response.text}")
    else:
        print("No users found to update")
else:
    print(f"Failed to get users: {response.status_code}")
    print(f"Response: {response.text}")