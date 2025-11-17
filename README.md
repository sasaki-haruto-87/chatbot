# チャットボット秘書（天気情報拡張版）

このプロジェクトは、スケジュール作成、忘れ物チェック、服装提案、食事記録を行う簡易チャットボット秘書のデモです。

## 必要環境
- Python 3.8+
- Windows PowerShell（以下の手順は PowerShell 向けです）

## セットアップ（PowerShell）
```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FLASK_APP='app.py'
python -m flask run
```

上記を実行後、ブラウザで http://127.0.0.1:5000 を開いてチャットで操作できます。

## サポートしている簡易コマンド例（チャット入力）
- スケジュール作成（構造化）: `スケジュール作成` ボタンはUIにありますが、チャットで送る場合はJSONデータで送ってください。
- 予定一覧: 「予定」または「次の予定」と入力
- 忘れ物確認: 「忘れ物」と入力（次の予定の持ち物を返します）
- 服装提案: 「服装 22」 のように気温を指定
- 食事記録: `食事記録` を使って記録（UIのフォームを推奨）

## 拡張アイデア
- 外部天気API連携で自動気温取得
	- 外部天気API連携で自動気温取得（OpenWeatherMap を利用）

## OpenWeatherMap を使った天気機能
このリポジトリは OpenWeatherMap の現在の天気を取得する機能を追加しています。事前に API キーが必要です。

1. 環境変数 `OPENWEATHER_API_KEY` に API キーを設定してください。
	 - PowerShell の例:
```powershell
$env:OPENWEATHER_API_KEY = 'あなたのAPIキー'
``` 
2. サーバーを起動して、トップページの「天気取得」フォームに都市名を入力してください（例: Tokyo, Osaka）。

### config.json に直接キーを置く方法（環境変数を使いたくない場合）
プロジェクトルートに `config.json` を作成し、次の形式で API キーを記述するとアプリはそれを優先して読み込みます（リポジトリにコミットすると危険なので注意してください）。

```json
{
	"OPENWEATHER_API_KEY": "あなたのAPIキー"
}
```

この方法を使う場合は `config.json` を `.gitignore` に追加することを推奨します。

API の呼び出しエンドポイントは `/api/weather` です。GET では `?city=Tokyo`、POST では JSON `{ "city": "Tokyo" }` で利用できます。

- 通知（メール・プッシュ）
- ユーザー認証・マルチユーザー

