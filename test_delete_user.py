import httpx
import json

# First get a user to delete (we'll create one specifically for this test)
# First create a user to delete
create_data = {
    "fullName": "User To Delete",
    "email": "delete@example.com",
    "role": "User",
    "status": "Active",
    "password": "delete123"
}

create_response = httpx.post(
    "http://localhost:8000/api/users",
    json=create_data,
    headers={"Content-Type": "application/json"}
)

if create_response.status_code == 200:
    created_user = create_response.json()
    user_id = created_user["id"]
    print(f"Created user for deletion test: {user_id}")
    
    # Now delete the user
    delete_response = httpx.delete(
        f"http://localhost:8000/api/users/{user_id}"
    )
    print(f"Delete Status: {delete_response.status_code}")
    print(f"Delete Response: {delete_response.text}")
    
    # Verify it's deleted by trying to get it
    get_response = httpx.get(f"http://localhost:8000/api/users/{user_id}")
    print(f"Get deleted user Status: {get_response.status_code}")
    if get_response.status_code == 404:
        print("User successfully deleted (404 as expected)")
    else:
        print(f"Get deleted user Response: {get_response.text}")
else:
    print(f"Failed to create user: {create_response.status_code}")
    print(f"Response: {create_response.text}")