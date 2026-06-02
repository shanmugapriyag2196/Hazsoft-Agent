import httpx
import json
import time

print("=== Testing Complete User Lifecycle ===")

# 1. Create a new user
print("\n1. Creating new user...")
create_data = {
    "fullName": "Lifecycle Test User",
    "email": "lifecycle@example.com",
    "role": "User",
    "status": "Active",
    "password": "lifecycle123"
}

create_response = httpx.post(
    "http://localhost:8000/api/users",
    json=create_data,
    headers={"Content-Type": "application/json"}
)

if create_response.status_code != 200:
    print(f"FAILED to create user: {create_response.status_code}")
    print(f"Response: {create_response.text}")
    exit(1)

created_user = create_response.json()
user_id = created_user["id"]
print(f"SUCCESS: Created user with ID: {user_id}")

# 2. Get the user to verify it was created correctly
print("\n2. Verifying user creation...")
get_response = httpx.get("http://localhost:8000/api/users")
if get_response.status_code == 200:
    users = get_response.json()
    user = next((u for u in users if u["id"] == user_id), None)
    if user:
        print(f"SUCCESS: Found user - Name: {user['FullName']}, Email: {user['Email']}, Role: {user['Role']}, Status: {user['Status']}")
    else:
        print(f"FAILED: Could not find user with ID {user_id}")
        exit(1)
else:
    print(f"FAILED to get users: {get_response.status_code}")
    exit(1)

# 3. Update the user
print("\n3. Updating user...")
update_data = {
    "fullName": "Updated Lifecycle User",
    "email": "updated.lifecycle@example.com",
    "role": "Admin",
    "status": "Active",
    "password": "updatedlifecycle123"
}

update_response = httpx.put(
    f"http://localhost:8000/api/users/{user_id}",
    json=update_data,
    headers={"Content-Type": "application/json"}
)

if update_response.status_code != 200:
    print(f"FAILED to update user: {update_response.status_code}")
    print(f"Response: {update_response.text}")
    exit(1)

updated_user = update_response.json()
print(f"SUCCESS: Updated user - Name: {updated_user['fields']['FullName']}, Email: {updated_user['fields']['Email']}, Role: {updated_user['fields']['Role']}, Status: {updated_user['fields']['Status']}")

# 4. Verify the update by getting the user again
print("\n4. Verifying user update...")
get_response = httpx.get("http://localhost:8000/api/users")
if get_response.status_code == 200:
    users = get_response.json()
    user = next((u for u in users if u["id"] == user_id), None)
    if user and user["FullName"] == "Updated Lifecycle User" and user["Role"] == "Admin":
        print(f"SUCCESS: User update verified - Name: {user['FullName']}, Role: {user['Role']}")
    else:
        print(f"FAILED: User update not verified")
        exit(1)
else:
    print(f"FAILED to get users: {get_response.status_code}")
    exit(1)

# 5. Delete the user
print("\n5. Deleting user...")
delete_response = httpx.delete(f"http://localhost:8000/api/users/{user_id}")
if delete_response.status_code != 200:
    print(f"FAILED to delete user: {delete_response.status_code}")
    print(f"Response: {delete_response.text}")
    exit(1)

delete_result = delete_response.json()
if delete_result.get("deleted") != True:
    print(f"FAILED: Delete response indicates user not deleted: {delete_result}")
    exit(1)

print(f"SUCCESS: User deleted successfully")

# 6. Verify the user is deleted
print("\n6. Verifying user deletion...")
get_response = httpx.get("http://localhost:8000/api/users")
if get_response.status_code == 200:
    users = get_response.json()
    user = next((u for u in users if u["id"] == user_id), None)
    if user is None:
        print(f"SUCCESS: User deletion verified - user no longer in list")
    else:
        print(f"FAILED: User still found in list after deletion")
        exit(1)
else:
    print(f"FAILED to get users: {get_response.status_code}")
    exit(1)

print("\n=== ALL TESTS PASSED ===")
print("The user lifecycle (create -> read -> update -> delete) is working correctly!")