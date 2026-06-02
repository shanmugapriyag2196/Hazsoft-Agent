import httpx
import json

print("Testing simple create -> update -> verify cycle...")

# Create a user
print("\n1. Creating user...")
create_response = httpx.post(
    "http://localhost:8000/api/users",
    json={
        "fullName": "Test User",
        "email": "test@example.com",
        "role": "User",
        "status": "Active",
        "password": "temp123"
    }
)

if create_response.status_code != 200:
    print(f"FAILED to create user: {create_response.status_code}")
    print(f"Response: {create_response.text}")
    exit(1)

created_user = create_response.json()
user_id = created_user["id"]
print(f"SUCCESS: Created user with ID: {user_id}")

# Update the user
print(f"\n2. Updating user {user_id}...")
update_response = httpx.put(
    f"http://localhost:8000/api/users/{user_id}",
    json={
        "fullName": "Updated User",
        "email": "updated@example.com",
        "role": "Admin",
        "status": "Active",
        "password": "updated123"
    }
)

if update_response.status_code != 200:
    print(f"FAILED to update user: {update_response.status_code}")
    print(f"Response: {update_response.text}")
    exit(1)

updated_user = update_response.json()
print(f"SUCCESS: Updated user")
print(f"  FullName: {updated_user['fields']['FullName']}")
print(f"  Email: {updated_user['fields']['Email']}")
print(f"  Role: {updated_user['fields']['Role']}")
print(f"  Status: {updated_user['fields']['Status']}")

# Verify by getting all users
print(f"\n3. Verifying update...")
get_response = httpx.get("http://localhost:8000/api/users")
if get_response.status_code != 200:
    print(f"FAILED to get users: {get_response.status_code}")
    print(f"Response: {get_response.text}")
    exit(1)

users = get_response.json()
user = next((u for u in users if u["id"] == user_id), None)
if not user:
    print(f"FAILED: Could not find user with ID {user_id}")
    exit(1)

print(f"SUCCESS: Found user in list")
print(f"  FullName: {user['FullName']}")
print(f"  Email: {user['Email']}")
print(f"  Role: {user['Role']}")
print(f"  Status: {user['Status']}")

if (user['FullName'] == "Updated User" and 
    user['Email'] == "updated@example.com" and
    user['Role'] == "Admin" and
    user['Status'] == "Active"):
    print(f"\n✅ ALL TESTS PASSED!")
    print("The create -> update -> verify cycle works correctly.")
else:
    print(f"\n❌ TEST FAILED: Data doesn't match expected values")
    exit(1)