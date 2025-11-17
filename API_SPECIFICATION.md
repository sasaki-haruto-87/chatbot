# Chatbot API 仕様書

## 概要

このドキュメントは、Gemini などの外部システムが Flask バックエンドの機能を呼び出すための HTTP API を規定しています。

**ベース URL:** `http://localhost:5000` （開発環境）

---

## 1. 汎用関数呼び出しエンドポイント

### POST /api/assistant_call

**説明:**  
モード（profile/schedule/meal）とアクション種別（add/modify/delete/read）を指定して、汎用的に操作を実行します。操作内容は ActionLog に記録され、undo サポートの対象となります。

**リクエスト形式:**

```json
{
  "mode": <integer>,
  "type": <integer>,
  "data": <object|string|null>
}
```

**フィールド:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `mode` | integer | ✓ | 操作対象ドメイン。1=profile, 2=schedule, 5=meal |
| `type` | integer | ✓ | アクション種別。1=add, 2=modify, 3=delete, 4=read |
| `data` | object\|string\|null | ○* | 操作パラメータ。add/modify は object、delete は id（string or object）、read は filter または null |

### モード別仕様

#### **mode=1 : プロファイル操作**

プロファイルは JSON ファイル(`profiles/<name>.json`)として保存されます。

##### type=1 (ADD) - プロファイル追加

**リクエスト:**
```json
{
  "mode": 1,
  "type": 1,
  "data": {
    "nickname": "taro",
    "name": "太郎",
    "age": 30,
    "region": "Tokyo"
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "profile": {
    "nickname": "taro",
    "name": "太郎",
    "age": 30,
    "region": "Tokyo"
  }
}
```

**エラーレスポンス (400):**
```json
{
  "error": "profile data (object) required for add"
}
```

---

##### type=2 (MODIFY) - プロファイル変更

既存プロファイルをマージ更新します。`nickname` または `name` で指定対象を特定します。

**リクエスト:**
```json
{
  "mode": 1,
  "type": 2,
  "data": {
    "name": "太郎",
    "age": 31
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "profile": {
    "nickname": "taro",
    "name": "太郎",
    "age": 31,
    "region": "Tokyo"
  }
}
```

---

##### type=3 (DELETE) - プロファイル削除

`data` に name/nickname を含めるか、単に文字列で指定します。

**リクエスト例 1 (オブジェクト形式):**
```json
{
  "mode": 1,
  "type": 3,
  "data": {
    "name": "太郎"
  }
}
```

**リクエスト例 2 (文字列形式):**
```json
{
  "mode": 1,
  "type": 3,
  "data": "太郎"
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true
}
```

---

##### type=4 (READ) - プロファイル照会

`data` が null/空なら全プロファイル、name/nickname が指定されればその 1 件を返します。

**リクエスト例 1 (全件):**
```json
{
  "mode": 1,
  "type": 4,
  "data": null
}
```

**レスポンス (200 OK):**
```json
{
  "profiles": [
    { "nickname": "taro", "name": "太郎", "age": 30, "region": "Tokyo" },
    { "nickname": "hanako", "name": "花子", "age": 28, "region": "Osaka" }
  ]
}
```

**リクエスト例 2 (1 件指定):**
```json
{
  "mode": 1,
  "type": 4,
  "data": {
    "name": "太郎"
  }
}
```

**レスポンス (200 OK):**
```json
{
  "profile": {
    "nickname": "taro",
    "name": "太郎",
    "age": 30,
    "region": "Tokyo"
  }
}
```

---

#### **mode=2 : スケジュール操作**

スケジュールは SQLite DB(Schedule テーブル)に保存されます。

##### type=1 (ADD) - スケジュール作成

**リクエスト:**
```json
{
  "mode": 2,
  "type": 1,
  "data": {
    "title": "会議",
    "datetime": "2025-12-20 14:00",
    "location": "会議室 A",
    "items": ["資料", "ペン"],
    "status": "active",
    "alarm": "2025-12-20 13:50"
  }
}
```

**フィールド説明:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `title` | string | ✓ | スケジュール名 |
| `datetime` | string | ✓ | ISO 形式日時（例: 2025-12-20 14:00） |
| `location` | string | | 場所 |
| `items` | array[string] | | 持ち物リスト |
| `status` | string | | ステータス。デフォルト: "active"（active/completed/cancelled） |
| `alarm` | string | | アラーム時刻（ISO 形式） |

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "schedule": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "会議",
    "datetime": "2025-12-20 14:00",
    "location": "会議室 A",
    "items": ["資料", "ペン"],
    "created_at": "2025-11-17T10:30:00",
    "updated_at": "2025-11-17T10:30:00",
    "status": "active",
    "alarm": "2025-12-20T13:50:00"
  }
}
```

---

##### type=2 (MODIFY) - スケジュール変更

`id` は必須。変更したいフィールドのみ指定します。

**リクエスト:**
```json
{
  "mode": 2,
  "type": 2,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "items": ["資料", "ペン", "メモ帳"]
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "schedule": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "会議",
    "datetime": "2025-12-20 14:00",
    "location": "会議室 A",
    "items": ["資料", "ペン", "メモ帳"],
    "created_at": "2025-11-17T10:30:00",
    "updated_at": "2025-11-17T10:35:00",
    "status": "completed",
    "alarm": "2025-12-20T13:50:00"
  }
}
```

---

##### type=3 (DELETE) - スケジュール削除

`data` に id を指定します（文字列またはオブジェクト）。

**リクエスト:**
```json
{
  "mode": 2,
  "type": 3,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true
}
```

---

##### type=4 (READ) - スケジュール照会

`data` が null/空なら全件、id を指定すればその 1 件を返します。

**リクエスト例 1 (全件):**
```json
{
  "mode": 2,
  "type": 4,
  "data": null
}
```

**レスポンス (200 OK):**
```json
{
  "schedules": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "会議",
      "datetime": "2025-12-20 14:00",
      "location": "会議室 A",
      "items": ["資料", "ペン"],
      "created_at": "2025-11-17T10:30:00",
      "updated_at": "2025-11-17T10:30:00",
      "status": "active",
      "alarm": "2025-12-20T13:50:00"
    }
  ]
}
```

---

#### **mode=5 : 食事記録操作**

食事は SQLite DB(Meal テーブル)に保存されます。

##### type=1 (ADD) - 食事記録追加

**リクエスト:**
```json
{
  "mode": 5,
  "type": 1,
  "data": {
    "date": "2025-11-17 12:30",
    "meal_type": "昼",
    "items": "ご飯, 味噌汁, 焼魚",
    "calories": 650,
    "photos": ["photo1.jpg", "photo2.jpg"],
    "rating": 4,
    "notes": "美味しかった"
  }
}
```

**フィールド説明:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `date` | string | | 食事日時（デフォルト: 現在時刻） |
| `meal_type` | string | ✓ | 食事タイプ（朝/昼/夕など） |
| `items` | string | | メニュー（カンマ区切り等） |
| `calories` | integer | | カロリー（kcal） |
| `photos` | array[string] | | 写真 URL/パス |
| `rating` | integer | | 評価（1-5） |
| `notes` | string | | メモ |

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "meal": {
    "id": "660e8400-e29b-41d4-a716-446655440111",
    "date": "2025-11-17 12:30",
    "meal_type": "昼",
    "items": "ご飯, 味噌汁, 焼魚",
    "calories": 650,
    "created_at": "2025-11-17T12:30:00",
    "photos": ["photo1.jpg", "photo2.jpg"],
    "rating": 4,
    "notes": "美味しかった"
  }
}
```

---

##### type=2 (MODIFY) - 食事記録変更

`id` は必須。変更したいフィールドのみ指定します。

**リクエスト:**
```json
{
  "mode": 5,
  "type": 2,
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440111",
    "rating": 5,
    "notes": "想像以上に美味しかった"
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true,
  "meal": {
    "id": "660e8400-e29b-41d4-a716-446655440111",
    "date": "2025-11-17 12:30",
    "meal_type": "昼",
    "items": "ご飯, 味噌汁, 焼魚",
    "calories": 650,
    "created_at": "2025-11-17T12:30:00",
    "photos": ["photo1.jpg", "photo2.jpg"],
    "rating": 5,
    "notes": "想像以上に美味しかった"
  }
}
```

---

##### type=3 (DELETE) - 食事記録削除

**リクエスト:**
```json
{
  "mode": 5,
  "type": 3,
  "data": {
    "id": "660e8400-e29b-41d4-a716-446655440111"
  }
}
```

**レスポンス (200 OK):**
```json
{
  "ok": true
}
```

---

##### type=4 (READ) - 食事記録照会

**リクエスト例 1 (全件):**
```json
{
  "mode": 5,
  "type": 4,
  "data": null
}
```

**レスポンス (200 OK):**
```json
{
  "meals": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440111",
      "date": "2025-11-17 12:30",
      "meal_type": "昼",
      "items": "ご飯, 味噌汁, 焼魚",
      "calories": 650,
      "created_at": "2025-11-17T12:30:00",
      "photos": ["photo1.jpg", "photo2.jpg"],
      "rating": 4,
      "notes": "美味しかった"
    }
  ]
}
```

---

## 2. Undo エンドポイント

### POST /api/assistant_undo

**説明:**  
直近の未 undo アクションを巻き戻します。オプションで mode を指定して特定ドメインに限定できます。

**リクエスト形式:**

```json
{
  "mode": <integer(optional)>
}
```

**フィールド:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `mode` | integer | | ドメイン制限（1=profile, 2=schedule, 5=meal）。指定なしなら全ドメイン |

**レスポンス例 (200 OK):**
```json
{
  "ok": true,
  "result": {
    "ok": true,
    "info": "profile deleted"
  },
  "action": {
    "id": 42,
    "mode": 1,
    "action_type": 3,
    "payload": { "name": "太郎" },
    "inverse": {
      "op": "add",
      "mode": 1,
      "data": { "nickname": "taro", "name": "太郎", "age": 30, "region": "Tokyo" }
    },
    "created_at": "2025-11-17T10:35:00",
    "undone": true
  }
}
```

**エラーレスポンス:**

- **404 Not Found** - undo 対象のアクションがない
  ```json
  {
    "error": "no action to undo"
  }
  ```

- **400 Bad Request** - inverse 情報がない
  ```json
  {
    "error": "no inverse available for last action"
  }
  ```

---

## 3. エラーハンドリング

### 共通エラーレスポンス

| HTTP ステータス | 説明 |
|---|---|
| 200 OK | 成功 |
| 400 Bad Request | リクエスト形式エラー、バリデーション失敗 |
| 404 Not Found | 対象が見つからない（レコード不在など） |
| 500 Internal Server Error | サーバー側エラー |

**エラーレスポンス例:**
```json
{
  "error": "schedule not found"
}
```

---

## 4. ActionLog と Undo 機構

### ActionLog テーブル構造

| カラム | 型 | 説明 |
|---|---|---|
| `id` | INTEGER | 主キー |
| `mode` | INTEGER | ドメイン（1/2/5） |
| `action_type` | INTEGER | アクション種別（1/2/3） |
| `payload` | TEXT (JSON) | 実行時のリクエスト data |
| `inverse` | TEXT (JSON) | undo に使用する逆操作情報 |
| `created_at` | DATETIME | アクション実行時刻 |
| `undone` | BOOLEAN | undo 済みフラグ |

### Inverse オブジェクト形式

```json
{
  "op": "add|delete|update",
  "mode": <integer>,
  "data": <full-record-or-params>
}
```

**op 別動作:**
- **"add"** : data で指定されたレコード/ファイルを再作成（undo は削除）
- **"delete"** : data で指定されたレコード/ファイルを削除（undo は復元）
- **"update"** : data に変更前の完全レコードを保持（undo は復元）

---

## 5. 実装ノート

### 認証・認可

**現状:** 実装されていません。  
**推奨:** API キー検証またはトークンベース認証を追加してください（例: Header `X-API-Key`）

### バリデーション

- mode と type は必須で整数値
- data は operation に応じて object/string/null を適切に指定
- datetime は ISO 8601 形式（`YYYY-MM-DDTHH:MM:SS` など）

### パフォーマンス

- ActionLog は全アクションを記録するため、大規模運用環境では定期的なアーカイブ/削除を検討

### セキュリティ考慮

- プロファイルやメモは個人情報を含む可能性があるため、ActionLog に保存される inverse データの取扱いに注意
- 必要に応じてアクセス制御ログやデータ暗号化を実装

---

## 6. 使用例（curl）

### プロファイル追加

```bash
curl -X POST http://localhost:5000/api/assistant_call \
  -H "Content-Type: application/json" \
  -d '{
    "mode": 1,
    "type": 1,
    "data": {
      "nickname": "taro",
      "name": "太郎",
      "age": 30,
      "region": "Tokyo"
    }
  }'
```

### スケジュール全件取得

```bash
curl -X POST http://localhost:5000/api/assistant_call \
  -H "Content-Type: application/json" \
  -d '{
    "mode": 2,
    "type": 4,
    "data": null
  }'
```

### Undo（最後のアクションを巻き戻す）

```bash
curl -X POST http://localhost:5000/api/assistant_undo \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Undo（プロファイル操作のみ限定）

```bash
curl -X POST http://localhost:5000/api/assistant_undo \
  -H "Content-Type: application/json" \
  -d '{
    "mode": 1
  }'
```

---

## 7. 変更履歴

| 日付 | 版 | 内容 |
|---|---|---|
| 2025-11-17 | 1.0 | 初版作成。assistant_call、assistant_undo エンドポイント定義 |

