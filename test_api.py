#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API 対話型テストスクリプト
mode=1（プロファイル操作）のテスト
"""
import requests
import json
import time

BASE_URL = "http://localhost:5000/api/assistant_call"

def test_profile():
    print("=" * 70)
    print("📋 mode=1（プロファイル操作）テスト")
    print("=" * 70)
    
    # ステップ 1: type=4 (READ) - セッション内プロファイル取得
    print("\n【ステップ 1】type=4 (READ) - セッション内プロファイル取得")
    print("-" * 70)
    
    payload = {
        "mode": 1,
        "type": 4,
        "data": None
    }
    
    try:
        r = requests.post(BASE_URL, json=payload, timeout=5)
        print(f"Status Code: {r.status_code}")
        print(f"Response:\n{json.dumps(r.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False
    
    print("\n✅ テスト完了")
    return True

if __name__ == '__main__':
    try:
        test_profile()
    except KeyboardInterrupt:
        print("\n🛑 ユーザーが中断しました")
