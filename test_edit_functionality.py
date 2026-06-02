import httpx
import json

print("=== Testing Edit (PUT) User Functionality ===")

# First, let's get a user to update
print("\n1. Getting list of users...")
get_response = httpx.get("http://localhost:8000/api/users")
if get_response.status_code != 200:
    print(f"FAILED to get users: {get_response.status_code}")
    print(f"Response: {get_response.text}")
    exit(1)

users = get_response.json()
if not users:
    print("No users found to test edit functionality")
    # Create a test user first
    print("\n2. Creating a test user...")
    create_data = {
        "fullName": "Edit Test User",
        "email": "edittest@example.com",
        "role": "User",
        "status": "Active",
        "password": "test123"
    }
    
    create_response = httpx.post(
        "http://localhost:8000/api/users",
        json=create_data,
        headers={"Content-Type": "application/json"}
    )
    
    if create_response.status_code != 200:
        print(f"FAILED to create test user: {create_response.status_code}")
        print(f"Response: {create_response.text}")
        exit(1)
    
    created_user = create_response.json()
    test_user_id = created_user["id"]
    print(f"SUCCESS: Created test user with ID: {test_user_id}")
    
    # Use this user for testing
    user_id = test_user_id
else:
    # Use the first user for testing
    user_id = users[0]["id"]
    print(f"Using existing user with ID: {user_id} for testing")

# Get the current user data to verify what we're updating
print(f"\n3. Getting current data for user ID: {user_id}")
get_user_response = httpx.get(f"http://localhost:8000/api/users")
if get_user_response.status_code == 200:
    all_users = get_user_response.json()
    user_data = next((u for u in all_users if u["id"] == user_id), None)
    if user_data:
        print(f"Current user data: {user_data}")
    else:
        print(f"FAILED: Could not find user with ID {user_id}")
        exit(1)
else:
    print(f"FAILED to get users: {get_user_response.status_code}")
    print(f"Response: {get_user_response.text}")
    exit(1)

# Now test the update
print(f"\n4. Testing update for user ID: {user_id}")
update_data = {
    "fullName": "Updated Edit Test User",
    "email": "updated.edittest@example.com",
    "role": "Admin",
    "status": "Active",
    "password": "updated123"
}

print(f"Sending update data: {update_data}")

put_response = httpx.put(
    f"http://localhost:8000/api/users/{user_id}",
    json=update_data,
    headers={"Content-Type": "application/json"}
)

print(f"PUT Response Status: {put_response.status_code}")
print(f"PUT Response Text: {put_response.text}")

if put_response.status_code == 200:
    updated_user = put_response.json()
    print(f"SUCCESS: User updated successfully")
    print(f"Updated user data: {updated_user}")
    
    # Verify the update by getting the user again
    print(f"\n5. Verifying update...")
    verify_response = httpx.get("http://localhost:8000/api/users")
    if verify_response.status_code == 200:
        updated_users = verify_response.json()
        verified_user = next((u for u in updated_users if u["id"] == user_id), None)
        if verified_user:
            print(f"VERIFIED: User data after update:")
            print(f"  ID: {verified_user['id']}")
            print(f"  FullName: {verified_user['FullName']}")
            print(f"  Email: {verified_user['Email']}")
            print(f"  Role: {verified_user['Role']}")
            print(f"  Status: {verified_user['Status']}")
            
            # Check if the update was applied correctly
            if (verified_user['FullName'] == "Updated Edit Test User" and 
                verified_user['Email'] == "updated.edittest@example.com" and
                verified_user['Role'] == "Admin" and
                verified_user['Status'] == "Active"):
                print(f"SUCCESS: Update verified correctly!")
            else:
                print(f"FAILED: Update data does not match expected values")
        else:
            print(f"FAILED: Could not find user with ID {user_id} after update")
    else:
        print(f"FAILED to verify update: {verify_response.status_code}")
        print(f"Response: {verify_response.text}")
else:
    print(f"FAILED to update user: {put_response.status_code}")
    print(f"Response: {put_response.text}")

print("\n=== Test Complete ===")