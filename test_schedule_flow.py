#!/usr/bin/env python
"""
Test schedule flow with API endpoint
mode=2: schedule operations
type=1: add, type=2: modify, type=3: delete, type=4: read
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = 'http://localhost:5000'

# Create a session to maintain cookies (session ID)
session = requests.Session()

print("=== Test: Schedule Flow (ADD -> READ -> MODIFY -> DELETE -> UNDO) ===\n")

# Generate a future datetime for testing
future_dt = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d 14:00')

# 1. ADD (type=1) - Add schedule
print("1. ADD スケジュール (type=1)")
payload = {
    'mode': 2,
    'type': 1,
    'data': {
        'title': '会議',
        'datetime': future_dt,
        'location': '会議室A',
        'items': ['資料', 'ノート', 'ペン'],
        'status': 'active'
    }
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
result = r.json()
print(f"Response: {json.dumps(result, indent=2, ensure_ascii=False)}\n")

# Extract schedule ID for later use
schedule_id = result.get('schedule', {}).get('id')
if not schedule_id:
    print("ERROR: Schedule ID not found in response")
    exit(1)
print(f"Schedule ID: {schedule_id}\n")

# 2. READ (type=4) - Read all schedules
print("2. READ スケジュール (type=4) - すべてのスケジュール")
payload = {
    'mode': 2,
    'type': 4,
    'data': None
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 3. READ specific schedule by ID
print(f"3. READ スケジュール (type=4) - 特定のスケジュール (ID: {schedule_id})")
payload = {
    'mode': 2,
    'type': 4,
    'data': {'id': schedule_id}
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 4. MODIFY (type=2) - Update schedule
print("4. MODIFY スケジュール (type=2) - タイトルと持ち物を変更")
payload = {
    'mode': 2,
    'type': 2,
    'data': {
        'id': schedule_id,
        'title': '重要な会議',
        'items': ['資料', 'ノート', 'ペン', 'パソコン']
    }
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 5. READ after modify
print("5. READ スケジュール (type=4) - 変更後の確認")
payload = {
    'mode': 2,
    'type': 4,
    'data': {'id': schedule_id}
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 6. DELETE (type=3) - Delete schedule
print("6. DELETE スケジュール (type=3)")
payload = {
    'mode': 2,
    'type': 3,
    'data': schedule_id
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 7. READ after delete
print("7. READ スケジュール (type=4) - 削除後")
payload = {
    'mode': 2,
    'type': 4,
    'data': {'id': schedule_id}
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 8. UNDO - Rollback deletion
print("8. UNDO (ロールバック - 削除を戻す)")
payload = {
    'mode': 2
}
r = session.post(f'{BASE_URL}/api/assistant_undo', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

# 9. READ after undo
print("9. READ スケジュール (type=4) - アンドウ後")
payload = {
    'mode': 2,
    'type': 4,
    'data': {'id': schedule_id}
}
r = session.post(f'{BASE_URL}/api/assistant_call', json=payload)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

print("=== All tests completed ===")
