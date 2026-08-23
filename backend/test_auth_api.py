import os
import sys
import django

# Setup django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()

def run_tests():
    print("==========================================")
    print("  DOXARANK AUTH API VERIFICATION SUITE   ")
    print("==========================================\n")
    
    client = APIClient()
    test_email = "intern_test@doxarank.com"
    test_password = "StrongPassword2026!"
    
    # Clean up test user if exists from prior runs
    User.objects.filter(email__iexact=test_email).delete()
    
    # 1. TEST REGISTRATION
    print("1. Testing Registration Endpoint (POST /api/auth/register/)...")
    reg_payload = {
        "email": test_email,
        "password": test_password,
        "first_name": "Antigravity",
        "last_name": "Tester"
    }
    reg_res = client.post('/api/auth/register/', reg_payload, format='json')
    assert reg_res.status_code == status.HTTP_201_CREATED, f"Registration failed: {reg_res.data}"
    assert 'tokens' in reg_res.data, "Tokens missing in registration response"
    assert 'access' in reg_res.data['tokens'] and 'refresh' in reg_res.data['tokens']
    assert reg_res.data['user']['email'] == test_email
    print(f"   [PASS] Registered successfully! Returned user: {reg_res.data['user']['email']}, Access Token: {reg_res.data['tokens']['access'][:20]}...")
    
    access_token = reg_res.data['tokens']['access']
    refresh_token = reg_res.data['tokens']['refresh']
    
    # 2. TEST DUPLICATE REGISTRATION
    print("\n2. Testing Duplicate Registration Prevention...")
    dup_res = client.post('/api/auth/register/', reg_payload, format='json')
    assert dup_res.status_code == status.HTTP_400_BAD_REQUEST, f"Duplicate registration should fail: {dup_res.status_code}"
    print("   [PASS] Duplicate registration rejected with 400 Bad Request.")
    
    # 3. TEST LOGIN (SUCCESS)
    print("\n3. Testing Login with Valid Credentials (POST /api/auth/login/)...")
    login_payload = {
        "email": test_email,
        "password": test_password
    }
    login_res = client.post('/api/auth/login/', login_payload, format='json')
    assert login_res.status_code == status.HTTP_200_OK, f"Login failed: {login_res.data}"
    assert 'tokens' in login_res.data
    print(f"   [PASS] Login successful! New access token issued.")
    
    # Update active access token
    access_token = login_res.data['tokens']['access']
    refresh_token = login_res.data['tokens']['refresh']
    
    # 4. TEST LOGIN (INVALID PASSWORD)
    print("\n4. Testing Login with Invalid Password...")
    bad_login_res = client.post('/api/auth/login/', {"email": test_email, "password": "WrongPassword!"}, format='json')
    assert bad_login_res.status_code == status.HTTP_400_BAD_REQUEST, "Invalid password should fail"
    print("   [PASS] Invalid password rejected with 400 Bad Request.")
    
    # 5. TEST PROTECTED ENDPOINT WITHOUT AUTH
    print("\n5. Testing Protected Endpoint Without Auth (GET /api/auth/me/)...")
    unauth_client = APIClient()
    me_unauth_res = unauth_client.get('/api/auth/me/')
    assert me_unauth_res.status_code == status.HTTP_401_UNAUTHORIZED, "Unauthenticated request must return 401"
    print("   [PASS] Unauthenticated access blocked with 401 Unauthorized.")
    
    # 6. TEST PROTECTED ENDPOINT WITH VALID BEARER TOKEN
    print("\n6. Testing Protected Endpoint With Bearer Token (GET /api/auth/me/)...")
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
    me_res = client.get('/api/auth/me/')
    assert me_res.status_code == status.HTTP_200_OK, f"Me endpoint failed: {me_res.data}"
    assert me_res.data['email'] == test_email
    assert me_res.data['full_name'] == "Antigravity Tester"
    print(f"   [PASS] Protected profile fetched successfully: {me_res.data}")
    
    # 7. TEST TOKEN REFRESH
    print("\n7. Testing Token Refresh (POST /api/auth/token/refresh/)...")
    refresh_res = client.post('/api/auth/token/refresh/', {"refresh": refresh_token}, format='json')
    assert refresh_res.status_code == status.HTTP_200_OK, f"Token refresh failed: {refresh_res.data}"
    assert 'access' in refresh_res.data
    new_access_token = refresh_res.data['access']
    # If rotated, get the new refresh token
    active_refresh_token = refresh_res.data.get('refresh', refresh_token)
    print(f"   [PASS] Token refreshed successfully! New Access Token: {new_access_token[:20]}...")
    
    # 8. TEST LOGOUT AND BLACKLISTING
    print("\n8. Testing Logout (POST /api/auth/logout/)...")
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access_token}')
    logout_res = client.post('/api/auth/logout/', {"refresh": active_refresh_token}, format='json')
    assert logout_res.status_code == status.HTTP_200_OK, f"Logout failed: {logout_res.data}"
    print(f"   [PASS] Logged out: {logout_res.data['detail']}")
    
    # 9. TEST BLACKLISTED TOKEN REJECTION
    print("\n9. Testing Blacklisted Token Cannot Be Reused...")
    reused_refresh_res = client.post('/api/auth/token/refresh/', {"refresh": active_refresh_token}, format='json')
    assert reused_refresh_res.status_code == status.HTTP_401_UNAUTHORIZED, "Blacklisted token should return 401"
    print("   [PASS] Blacklisted token rejected with 401 Unauthorized.")
    
    # Clean up test user
    User.objects.filter(email__iexact=test_email).delete()
    
    print("\n==========================================")
    print("   ALL 9 AUTH API TESTS PASSED! (100%)    ")
    print("==========================================\n")

if __name__ == '__main__':
    run_tests()
