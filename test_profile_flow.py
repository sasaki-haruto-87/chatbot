#!/usr/bin/env python
"""
Test profile flow with same session (using requests.Session)
"""
import requests
import json

BASE_URL = 'http://localhost:5000'

# Create a session to maintain cookies (session ID)
session = requests.Session()

print("=== Test: Profile Flow (ADD -> MODIFY -> READ -> DELETE -> UNDO) ===\n")

# 1. ADD (type=1) - Add profile to session
print("1. ADD プロファイル (type=1)")
payload = {
    'mode': 1,
    'type': 1,
    'data': {
        'nickname': 'taro',
        'age': 30,
        'region': 'Tokyo'
    }
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 2. READ (type=4) - Read profile from session
print("2. READ プロファイル (type=4) - セッション内の値を確認")
payload = {
    'mode': 1,
    'type': 4,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 3. MODIFY (type=2) - Update profile
print("3. MODIFY プロファイル (type=2) - 年齢を35に変更")
payload = {
    'mode': 1,
    'type': 2,
    'data': {
        'age': 35
    }
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 4. READ again
print("4. READ プロファイル (type=4) - 変更後の値を確認")
payload = {
    'mode': 1,
    'type': 4,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 5. DELETE (type=3) - Delete profile
print("5. DELETE プロファイル (type=3)")
payload = {
    'mode': 1,
    'type': 3,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 6. READ after delete
print("6. READ プロファイル (type=4) - 削除後")
payload = {
    'mode': 1,
    'type': 4,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 7. UNDO - Rollback last operation
print("7. UNDO (ロールバック)")
payload = {
    'mode': 1,
    'type': 3
}
r = session.post(f'{BASE_URL}/api/assistant_undo', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 8. READ after undo
print("8. READ プロファイル (type=4) - アンドウ後")
payload = {
    'mode': 1,
    'type': 4,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

print("=== All tests completed ===")
