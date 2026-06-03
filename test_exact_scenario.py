import requests
import json
import time

print("Testing exact user scenario: Full Name: Shanmuga, Email: abc@gmail.com, Role: Admin, Status: Active")

# Test creating a user with the exact data the user specified
user_data = {
    "fullName": "Shanmuga",
    "email": "abc@gmail.com",
    "role": "Admin",
    "status": "Active",
    "password": "temp123"  # This will be auto-generated in the form
}

try:
    print("\n1. Creating user with specified data...")
    response = requests.post(
        "http://localhost:8000/api/users",
        json=user_data,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        created_user = response.json()
        print(f"SUCCESS: User created!")
        print(f"User ID: {created_user['id']}")
        print(f"FullName: {created_user['fields']['FullName']}")
        print(f"Email: {created_user['fields']['Email']}")
        print(f"Role: {created_user['fields']['Role']}")
        print(f"Status: {created_user['fields']['Status']}")
        print(f"Password: {created_user['fields']['Password']}")
        
        # Verify the data matches exactly what was requested
        expected_data = {
            "FullName": "Shanmuga",
            "Email": "abc@gmail.com",
            "Role": "Admin",
            "Status": "Active"
        }
        
        actual_data = {
            "FullName": created_user['fields']['FullName'],
            "Email": created_user['fields']['Email'],
            "Role": created_user['fields']['Role'],
            "Status": created_user['fields']['Status']
        }
        
        if actual_data == expected_data:
            print(f"\n✅ DATA VERIFICATION PASSED: All fields match exactly what was requested!")
        else:
            print(f"\n❌ DATA VERIFICATION FAILED:")
            print(f"Expected: {expected_data}")
            print(f"Actual:   {actual_data}")
            
    else:
        print(f"FAILED to create user: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"Error: {e}")

# Now let's verify by getting all users and checking if our user is there
print("\n2. Verifying user exists in the list...")
try:
    response = requests.get("http://localhost:8000/api/users")
    if response.status_code == 200:
        users = response.json()
        shanmuga_user = None
        for user in users:
            if user['fields'].get('FullName') == 'Shanmuga' and user['fields'].get('Email') == 'abc@gmail.com':
                shanmuga_user = user
                break
        
        if shanmuga_user:
            print(f"SUCCESS: Found Shanmuga's user in the list!")
            print(f"User ID: {shanmuga_user['id']}")
            print(f"FullName: {shanmuga_user['fields']['FullName']}")
            print(f"Email: {shanmuga_user['fields']['Email']}")
            print(f"Role: {shanmuga_user['fields']['Role']}")
            print(f"Status: {shanmuga_user['fields']['Status']}")
            print(f"Password: {shanmuga_user['fields']['Password']}")
        else:
            print("FAILED: Could not find Shanmuga's user in the list")
            print("All users:")
            for user in users:
                print(f"  - {user['fields'].get('FullName', 'N/A')} ({user['fields'].get('Email', 'N/A')})")
    else:
        print(f"FAILED to get users: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"Error getting users: {e}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)