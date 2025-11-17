import os
import re
import json
import requests
import uuid
import socket
import struct
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'assistant.db')
PROFILE_DIR = os.path.join(BASE_DIR, 'profiles')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# セッション用の secret key（環境変数があればそれを使う）
app.secret_key = os.environ.get('FLASK_SECRET') or os.environ.get('SECRET_KEY') or os.urandom(24).hex()

db = SQLAlchemy(app)

# --- Models ---
class Schedule(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUIDv4
    title = db.Column(db.String(200), nullable=False)
    datetime = db.Column(db.String(100), nullable=False)  # ISO string
    location = db.Column(db.String(200), nullable=True)
    items_json = db.Column(db.Text, nullable=True)  # JSON list of items
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    status = db.Column(db.String(50), nullable=False, default='active')  # active, completed, cancelled
    alarm = db.Column(db.DateTime, nullable=True)  # アラーム時刻

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'datetime': self.datetime,
            'location': self.location,
            'items': json.loads(self.items_json) if self.items_json else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'status': self.status,
            'alarm': self.alarm.isoformat() if self.alarm else None
        }

class Meal(db.Model):
    id = db.Column(db.String(36), primary_key=True)  # UUIDv4
    date = db.Column(db.String(50), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    items = db.Column(db.Text, nullable=True)
    calories = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    photos = db.Column(db.Text, nullable=True)  # JSON array of photo URLs/paths
    rating = db.Column(db.Integer, nullable=True)  # 1-5 star rating
    notes = db.Column(db.Text, nullable=True)  # Optional notes about the meal

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'meal_type': self.meal_type,
            'items': self.items,
            'calories': self.calories,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'photos': json.loads(self.photos) if self.photos else [],
            'rating': self.rating,
            'notes': self.notes
        }


# Action log for undo support
class ActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.Integer, nullable=False)
    action_type = db.Column(db.Integer, nullable=False)  # 1:add,2:modify,3:delete
    payload = db.Column(db.Text, nullable=True)  # JSON of what was sent
    inverse = db.Column(db.Text, nullable=True)  # JSON describing how to undo
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    undone = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'mode': self.mode,
            'action_type': self.action_type,
            'payload': json.loads(self.payload) if self.payload else None,
            'inverse': json.loads(self.inverse) if self.inverse else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'undone': self.undone
        }

# --- Helpers ---
def init_db():
    try:
        # データベースが存在しない場合は作成
        if not os.path.exists(DB_PATH):
            db.create_all()
        else:
            # データベースは存在するがテーブルがない可能性があるため、テーブルを作成
            with app.app_context():
                db.create_all()
        
        # プロファイルディレクトリを作成
        if not os.path.exists(PROFILE_DIR):
            try:
                os.makedirs(PROFILE_DIR, exist_ok=True)
            except Exception:
                pass
    except Exception as e:
        print(f"データベース初期化エラー: {str(e)}")

# アプリ読み込み時にテーブルを確実に作成する（`flask run` で起動したときも対応）
try:
    with app.app_context():
        db.create_all()
        init_db()
except Exception as e:
    # 起動時に致命的なエラーとせずログだけ出す
    print(f'初期データベース初期化に失敗しました（続行）: {e}')


# --- OpenWeatherMap helper ---
def get_current_weather(city: str):
    """OpenWeatherMap の現在の天気を取得して簡易整形して返す。
    返り値: dict または None (失敗時)
    """
    # まずプロジェクトルートの config.json を確認し、そこに API キーがあれば優先して使う
    def _load_api_key_from_config():
        cfg_path = os.path.join(BASE_DIR, 'config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as fh:
                    cfg = json.load(fh)
                # 大文字・小文字両対応でキーを探す
                    return cfg.get('OPENWEATHER_API_KEY') or cfg.get('openweather_api_key')
            except Exception:
                # 読み込み失敗は無視して環境変数にフォールバック
                return None
        return None

    api_key = _load_api_key_from_config() or os.environ.get('OPENWEATHER_API_KEY')
    if not api_key:
        return {'error': 'OpenWeatherMap APIキーが見つかりません。config.json または環境変数 OPENWEATHER_API_KEY を設定してください。'}
    url = 'https://api.openweathermap.org/data/2.5/weather'
    params = {
        'q': city,
        'appid': api_key,
        'units': 'metric',
        'lang': 'ja'
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        j = resp.json()
        # 必要な情報のみ抽出
        weather = {
            'city': f"{j.get('name', '')}{',' + j['sys'].get('country') if j.get('sys') else ''}",
            'temp': j.get('main', {}).get('temp'),
            'feels_like': j.get('main', {}).get('feels_like'),
            'description': j.get('weather', [{}])[0].get('description'),
            'humidity': j.get('main', {}).get('humidity'),
            'wind_speed': j.get('wind', {}).get('speed')
        }
        return {'weather': weather}
    except requests.RequestException as e:
        return {'error': f'天気情報の取得に失敗しました: {str(e)}'}


# --- Profile helpers ---
def _profile_path(name: str):
    safe = re.sub(r"[^0-9A-Za-z_\-\u4E00-\u9FFF\u3040-\u30FF ]", "_", name)
    return os.path.join(PROFILE_DIR, f"{safe}.json")

def save_profile(profile: dict):
    name = profile.get('nickname') or profile.get('name')
    if not name:
        raise ValueError('nickname is required')
    path = _profile_path(name)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=2)
    return profile

def load_profile(name: str):
    path = _profile_path(name)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)

def list_profiles():
    items = []
    if not os.path.exists(PROFILE_DIR):
        return items
    for fn in os.listdir(PROFILE_DIR):
        if fn.endswith('.json'):
            try:
                with open(os.path.join(PROFILE_DIR, fn), 'r', encoding='utf-8') as fh:
                    p = json.load(fh)
                    items.append(p)
            except Exception:
                continue
    return items


# --- Time helpers (NTP) ---
def _load_config():
    cfg_path = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def get_ntp_server():
    # 優先順: config.json -> 環境変数 -> デフォルト
    cfg = _load_config()
    return cfg.get('NTP_SERVER') or os.environ.get('NTP_SERVER') or 'ntp1.jst.mfeed.ad.jp'


def get_ntp_time(server: str = None, timeout: float = 3.0):
    """NTP サーバから時刻を取得する。失敗したら例外を投げる。
    返り値: dict { 'utc': ISO, 'local': ISO, 'timestamp': float }
    """
    if not server:
        server = get_ntp_server()

    port = 123
    # NTPパケット (LI=0 VN=3 Mode=3) -> 0x1B
    msg = b'\x1b' + 47 * b'\0'
    try:
        addr = socket.gethostbyname(server)
    except Exception as e:
        raise RuntimeError(f"NTP ホスト解決失敗: {e}")

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(msg, (addr, port))
        data, _ = s.recvfrom(48)
    except socket.timeout:
        raise RuntimeError('NTP 応答がタイムアウトしました')
    except Exception as e:
        raise RuntimeError(f'NTP 取得エラー: {e}')
    finally:
        try:
            s.close()
        except Exception:
            pass

    if len(data) < 48:
        raise RuntimeError('NTP 応答が不正です')

    # unpack 12 32-bit unsigned ints (ネットワークバイトオーダー)
    try:
        unpacked = struct.unpack('!12I', data)
        transmit_seconds = unpacked[10]
        transmit_fraction = unpacked[11]
        # NTP epoch -> Unix epoch
        NTP_DELTA = 2208988800
        seconds = float(transmit_seconds - NTP_DELTA) + float(transmit_fraction) / 2**32
        utc_dt = datetime.utcfromtimestamp(seconds)
        local_dt = datetime.fromtimestamp(seconds)
        return {'utc': utc_dt.isoformat(), 'local': local_dt.isoformat(), 'timestamp': seconds}
    except Exception as e:
        raise RuntimeError(f'NTP レスポンス解析エラー: {e}')


# --- Action logging helpers ---
def _record_action(mode:int, action_type:int, payload_obj, inverse_obj):
    try:
        al = ActionLog(
            mode=int(mode),
            action_type=int(action_type),
            payload=json.dumps(payload_obj, ensure_ascii=False) if payload_obj is not None else None,
            inverse=json.dumps(inverse_obj, ensure_ascii=False) if inverse_obj is not None else None
        )
        db.session.add(al)
        db.session.commit()
        return al.to_dict()
    except Exception as e:
        print(f"ActionLog error: {e}")
        db.session.rollback()
        return None


def _apply_inverse(inverse_obj):
    """
    inverse_obj should be a dict with keys: op ('add'|'update'|'delete'), mode, data
    """
    if not inverse_obj or not isinstance(inverse_obj, dict):
        raise RuntimeError('invalid inverse object')

    op = inverse_obj.get('op')
    mode = inverse_obj.get('mode')
    data = inverse_obj.get('data')

    # Profile operations (mode==1) - セッションベース
    if mode == 1:
        if op == 'add':
            # セッション内プロファイルを復元
            from flask import session
            session['profile'] = data
            return {'ok': True, 'info': 'profile restored'}
        if op == 'delete':
            # セッション内プロファイルをクリア
            from flask import session
            session.pop('profile', None)
            return {'ok': True, 'info': 'profile cleared'}
        if op == 'update':
            # セッション内プロファイルを復元
            from flask import session
            session['profile'] = data
            return {'ok': True, 'info': 'profile restored'}

    # Schedule operations (mode==2)
    if mode == 2:
        if op == 'delete':
            # delete schedule by id
            sid = data.get('id')
            s = Schedule.query.get(sid)
            if s:
                db.session.delete(s)
                db.session.commit()
            return {'ok': True, 'info': 'schedule deleted'}
        if op == 'add':
            # recreate schedule from full data
            s = Schedule(
                id=data.get('id') or str(uuid.uuid4()),
                title=data.get('title',''),
                datetime=data.get('datetime',''),
                location=data.get('location'),
                items_json=json.dumps(data.get('items',[]), ensure_ascii=False),
                status=data.get('status','active'),
                alarm=datetime.fromisoformat(data['alarm']) if data.get('alarm') else None
            )
            db.session.add(s)
            db.session.commit()
            return {'ok': True, 'info': 'schedule restored', 'schedule': s.to_dict()}
        if op == 'update':
            # data contains previous full record
            sid = data.get('id')
            s = Schedule.query.get(sid)
            if not s:
                # recreate
                return _apply_inverse({'op':'add','mode':2,'data':data})
            s.title = data.get('title')
            s.datetime = data.get('datetime')
            s.location = data.get('location')
            s.items_json = json.dumps(data.get('items',[]), ensure_ascii=False)
            s.status = data.get('status','active')
            try:
                s.alarm = datetime.fromisoformat(data['alarm']) if data.get('alarm') else None
            except Exception:
                s.alarm = None
            db.session.commit()
            return {'ok': True, 'info': 'schedule restored'}

    # Meal operations (mode==5)
    if mode == 5:
        if op == 'delete':
            mid = data.get('id')
            m = Meal.query.get(mid)
            if m:
                db.session.delete(m)
                db.session.commit()
            return {'ok': True, 'info': 'meal deleted'}
        if op == 'add':
            mm = Meal(
                id=data.get('id') or str(uuid.uuid4()),
                date=data.get('date') or datetime.now().strftime('%Y-%m-%d %H:%M'),
                meal_type=data.get('meal_type','不明'),
                items=data.get('items',''),
                calories=data.get('calories'),
                photos=json.dumps(data.get('photos')) if data.get('photos') else None,
                rating=data.get('rating'),
                notes=data.get('notes')
            )
            db.session.add(mm)
            db.session.commit()
            return {'ok': True, 'info': 'meal restored', 'meal': mm.to_dict()}
        if op == 'update':
            mid = data.get('id')
            m = Meal.query.get(mid)
            if not m:
                return _apply_inverse({'op':'add','mode':5,'data':data})
            m.meal_type = data.get('meal_type','不明')
            m.items = data.get('items','')
            m.calories = data.get('calories')
            m.photos = json.dumps(data.get('photos')) if data.get('photos') else None
            m.rating = data.get('rating')
            m.notes = data.get('notes')
            db.session.commit()
            return {'ok': True, 'info': 'meal restored'}

    raise RuntimeError('unsupported inverse operation')


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    payload = request.get_json() or {}
    message = (payload.get('message') or '').strip()

    # プロファイル情報がペイロードにあれば取り出す（クライアントは profile を JSON オブジェクトで送る）
    profile_payload = payload.get('profile')
    profile_obj = {}
    if isinstance(profile_payload, dict):
        profile_obj = profile_payload
    elif profile_payload:
        # 文字列の場合はサーバーに保存されたプロファイル名として読み込む（互換）
        p = load_profile(profile_payload)
        if p:
            profile_obj = p

    # クライアントから送られたプロファイルをセッションに登録
    if profile_obj:
        session['profile'] = profile_obj

    # 会話形式のプロファイル登録フロー（セッションで管理）
    flow = session.get('profile_flow')
    if message in ('プロファイル登録', 'プロフィール登録'):
        session['profile_flow'] = 'await_name'
        session['temp_profile'] = {}
        return jsonify({'reply': '名前は？'})

    if flow == 'await_name':
        name = message.strip()
        if not name:
            return jsonify({'reply': '名前を入力してください。'})
        tp = session.get('temp_profile', {})
        tp['name'] = name
        tp['nickname'] = tp.get('nickname') or name
        session['temp_profile'] = tp
        session['profile_flow'] = 'await_age'
        return jsonify({'reply': '年齢は？（数字で入力してください）'})

    if flow == 'await_age':
        m = re.search(r'(\d{1,3})', message)
        if not m:
            return jsonify({'reply': '年齢は数字で入力してください（例: 30）'})
        age_val = int(m.group(1))
        tp = session.get('temp_profile', {})
        tp['age'] = age_val
        session['temp_profile'] = tp
        session['profile_flow'] = 'await_region'
        return jsonify({'reply': '地域は？'})

    if flow == 'await_region':
        region = message.strip()
        if not region:
            return jsonify({'reply': '地域名を入力してください。'})
        tp = session.get('temp_profile', {})
        tp['region'] = region
        # フロー完了
        session.pop('profile_flow', None)
        session.pop('temp_profile', None)
        # サーバーからプロファイルを返す（クライアントはこれを保存）
        return jsonify({'reply': f'プロファイル登録が完了しました: {tp.get("name")} / {tp.get("age")} / {tp.get("region")}', 'profile': tp})

    # --- メニュー駆動の登録/変更/削除フロー ---
    # トップメニュー開始
    if message in ('登録', '変更', '削除'):
        session['menu_action'] = message  # '登録' / '変更' / '削除'
        menu = (
            '何を{}しますか？番号で選んでください:\n'
            '1. プロファイル\n'
            '2. 予定\n'
            '3. 忘れ物(予定の持ち物に追加)\n'
            '4. 服装(メモ)\n'
            '5. 食事記録\n'
            '6. 地域'
        ).format(message)
        return jsonify({'reply': menu})

    # メニュー選択の処理 (選択は数字か単語で受け付ける)
    menu_action = session.get('menu_action')
    if menu_action:
        # ユーザーがキャンセルしたい場合
        if message in ('キャンセル', 'やめる', '中止'):
            session.pop('menu_action', None)
            # 可能ならフロー中の一時データも消す
            for k in ('temp_schedule', 'register_schedule_flow', 'temp_meal', 'register_meal_flow'):
                session.pop(k, None)
            return jsonify({'reply': '操作をキャンセルしました。'})

        choice = None
        m_num = re.match(r'^(\d)$', message.strip())
        if m_num:
            choice = int(m_num.group(1))
        else:
            # キーワードでも受け付け
            mapping = {'プロファイル':1, '予定':2, '忘れ物':3, '服装':4, '食事':5, '地域':6}
            for k,v in mapping.items():
                if k in message:
                    choice = v
                    break

        if not choice:
            return jsonify({'reply': '番号で選択してください（例: 1）またはキャンセルと入力してください。'})

        # 登録フローを開始
        if menu_action == '登録':
            if choice == 1:
                # プロファイル登録 → 再利用: セッションベースのプロファイル登録を開始
                session.pop('menu_action', None)
                session['profile_flow'] = 'await_name'
                session['temp_profile'] = {}
                return jsonify({'reply': 'プロファイル登録を開始します。名前は？'})
            elif choice == 2:
                # スケジュール登録のQ&Aを開始
                session.pop('menu_action', None)
                session['register_schedule_flow'] = 'await_title'
                session['temp_schedule'] = {}
                return jsonify({'reply': 'スケジュール登録を開始します。タイトルは？'})
            elif choice == 3:
                session.pop('menu_action', None)
                return jsonify({'reply': '忘れ物の登録は、予定の持ち物として追加します。対象の予定IDを入力するか「次の予定」と入力してください。'})
            elif choice == 4:
                session.pop('menu_action', None)
                return jsonify({'reply': '服装メモは「服装 22」のように入力してください。保存はクライアント側で管理してください。'})
            elif choice == 5:
                # 食事登録のQ&Aを開始
                session.pop('menu_action', None)
                session['register_meal_flow'] = 'await_type'
                session['temp_meal'] = {}
                return jsonify({'reply': '食事記録登録を開始します。食事タイプは？（例: 朝/昼/夕）'})
            elif choice == 6:
                session.pop('menu_action', None)
                session['profile_flow'] = 'await_region'
                session['temp_profile'] = {}
                return jsonify({'reply': '地域を入力してください。'})

        # 変更フロー: 簡易実装 (プロフィールはクライアント管理のため案内のみ)
        if menu_action == '変更':
            session.pop('menu_action', None)
            if choice == 1:
                return jsonify({'reply': 'プロファイルの変更はクライアントで行ってください。画面のプロファイル編集機能を使ってください。'})
            elif choice == 2:
                return jsonify({'reply': '予定の変更は予定一覧から ID を確認し、API を使って更新してください（例: PUT /api/schedules）。またはチャットで「予定」を入力して該当予定を確認してください。'})
            elif choice == 3:
                return jsonify({'reply': '忘れ物の変更は該当予定の持ち物を編集してください（予定を編集 -> items を更新）。'})
            elif choice == 4:
                return jsonify({'reply': '服装メモの変更は現在サポートされていません。'})
            elif choice == 5:
                return jsonify({'reply': '食事記録の変更は該当の記録 ID を指定して PUT /api/meals を使用してください。'})
            elif choice == 6:
                return jsonify({'reply': '地域の変更は「地域登録 <地域名>」で行えます（例: 地域登録 Tokyo）。'})

        # 削除フロー
        if menu_action == '削除':
            session.pop('menu_action', None)
            if choice == 1:
                return jsonify({'reply': 'プロファイルの削除はクライアント側で行ってください（ローカルストレージのプロファイルを削除）。'})
            elif choice == 2:
                return jsonify({'reply': '予定を削除するには「予定削除 <ID>」と入力してください。予定の ID は「予定」と入力して確認できます。'})
            elif choice == 3:
                return jsonify({'reply': '忘れ物は予定の持ち物を編集して削除してください。'})
            elif choice == 4:
                return jsonify({'reply': '服装メモの削除はサポートされていません。'})
            elif choice == 5:
                return jsonify({'reply': '食事記録を削除するには「食事削除 <ID>」と入力してください。記録の ID は「食事」と入力して確認できます。'})
            elif choice == 6:
                return jsonify({'reply': '地域情報の削除はクライアント側で行ってください。'})

    # スケジュール登録 Q&A フロー
    sch_flow = session.get('register_schedule_flow')
    if sch_flow:
        ts = session.get('temp_schedule', {})
        if sch_flow == 'await_title':
            ts['title'] = message.strip() or '無題'
            session['temp_schedule'] = ts
            session['register_schedule_flow'] = 'await_datetime'
            return jsonify({'reply': '日時を入力してください（例: 2025-10-30 14:00）'})
        if sch_flow == 'await_datetime':
            try:
                # 確認だけするためパースする
                _ = datetime.fromisoformat(message.strip())
                ts['datetime'] = message.strip()
                session['temp_schedule'] = ts
                session['register_schedule_flow'] = 'await_items'
                return jsonify({'reply': '持ち物があればカンマ区切りで入力してください。なければ空で送ってください。'})
            except Exception:
                return jsonify({'reply': '日時の形式が不正です。例: 2025-10-30 14:00 のように入力してください。'})
        if sch_flow == 'await_items':
            items = [i.strip() for i in message.split(',') if i.strip()]
            ts['items'] = items
            session['temp_schedule'] = ts
            session['register_schedule_flow'] = 'await_location'
            return jsonify({'reply': '場所があれば入力してください。なければ空で送ってください。'})
        if sch_flow == 'await_location':
            ts['location'] = message.strip()
            # 保存
            schedule_id = str(uuid.uuid4())
            s = Schedule(
                id=schedule_id,
                title=ts.get('title', '無題'),
                datetime=ts.get('datetime'),
                location=ts.get('location'),
                items_json=json.dumps(ts.get('items', []), ensure_ascii=False),
                status='active'
            )
            db.session.add(s)
            db.session.commit()
            # クリア
            session.pop('register_schedule_flow', None)
            session.pop('temp_schedule', None)
            return jsonify({'reply': f'スケジュールを作成しました: {s.title} @ {s.datetime}', 'schedule': s.to_dict()})

    # 食事登録 Q&A フロー
    meal_flow = session.get('register_meal_flow')
    if meal_flow:
        tm = session.get('temp_meal', {})
        if meal_flow == 'await_type':
            tm['meal_type'] = message.strip() or '不明'
            session['temp_meal'] = tm
            session['register_meal_flow'] = 'await_items'
            return jsonify({'reply': 'メニューを入力してください（カンマ区切り）。例: ご飯, 味噌汁'})
        if meal_flow == 'await_items':
            tm['items'] = message.strip()
            session['temp_meal'] = tm
            session['register_meal_flow'] = 'await_calories'
            return jsonify({'reply': 'カロリーが分かれば数字で入力してください。分からなければ空で送ってください。'})
        if meal_flow == 'await_calories':
            m = re.search(r'(\d+)', message)
            if m:
                tm['calories'] = int(m.group(1))
            else:
                tm['calories'] = None
            session['temp_meal'] = tm
            session['register_meal_flow'] = 'await_rating'
            return jsonify({'reply': '評価（1-5）を入力してください。なければ空で送ってください。'})
        if meal_flow == 'await_rating':
            m = re.search(r'([1-5])', message)
            if m:
                tm['rating'] = int(m.group(1))
            else:
                tm['rating'] = None
            # 保存
            meal_id = str(uuid.uuid4())
            mm = Meal(
                id=meal_id,
                date=datetime.now().strftime('%Y-%m-%d %H:%M'),
                meal_type=tm.get('meal_type', '不明'),
                items=tm.get('items', ''),
                calories=tm.get('calories'),
                photos=None,
                rating=tm.get('rating'),
                notes=None
            )
            db.session.add(mm)
            db.session.commit()
            session.pop('register_meal_flow', None)
            session.pop('temp_meal', None)
            reply = f'食事を記録しました: {mm.meal_type} — {mm.items}'
            if mm.calories:
                reply += f' ({mm.calories} kcal)'
            if mm.rating:
                reply += f'\n評価: {"★" * mm.rating}{"☆" * (5-mm.rating)}'
            return jsonify({'reply': reply, 'meal': mm.to_dict()})

    # チャットからプロファイル属性を設定・変更するパターンを検出して処理する
    # 例: "ニックネーム 太郎", "年齢 30", "地域 Tokyo"
    updated = False
    # ニックネーム
    m_nick = re.search(r'ニックネーム(?:を|は|:|：)?\s*([^\s。､,、!?？!]+)', message)
    if m_nick:
        profile_obj['nickname'] = m_nick.group(1).strip()
        updated = True
    # 年齢
    m_age = re.search(r'年齢(?:を|は|:|：)?\s*(\d{1,3})', message)
    if m_age:
        try:
            profile_obj['age'] = int(m_age.group(1))
            updated = True
        except Exception:
            pass
    # 地域
    m_region = re.search(r'地域(?:を|は|:|：)?\s*([^\s。､,、!?？!]+)', message)
    if m_region:
        profile_obj['region'] = m_region.group(1).strip()
        updated = True

    if updated:
        # 更新結果を返す（クライアントはこれを受け取ってローカルに保存しておく）
        return jsonify({'reply': 'プロファイルを更新しました。', 'profile': profile_obj})

    # 対話式プロファイル登録開始
    if message in ('プロファイル登録', 'プロフィール登録'):
        help_text = (
            'プロファイル登録を開始します。\n'
            "名前は '名前登録 太郎' のように入力してください。\n"
            "年齢は '年齢登録 30' のように入力してください。\n"
            "地域は '地域登録 Tokyo' のように入力してください。\n"
            "現在のプロファイルを保存するには、画面上の「プロファイル保存」ボタンを使ってください。"
        )
        return jsonify({'reply': help_text})

    # 名前登録コマンド: "名前登録 太郎"
    m_name_reg = re.match(r'名前登録\s+(.+)', message)
    if m_name_reg:
        name_val = m_name_reg.group(1).strip()
        if name_val:
            profile_obj['name'] = name_val
            # 互換として nickname も設定
            if not profile_obj.get('nickname'):
                profile_obj['nickname'] = name_val
            return jsonify({'reply': f'名前を登録しました: {name_val}', 'profile': profile_obj})
        else:
            return jsonify({'reply': "名前登録 の後に名前を入力してください（例: 名前登録 太郎）"})

    # 年齢登録コマンド: "年齢登録 30"
    m_age_reg = re.match(r'年齢登録\s+(\d{1,3})', message)
    if m_age_reg:
        try:
            age_val = int(m_age_reg.group(1))
            profile_obj['age'] = age_val
            return jsonify({'reply': f'年齢を登録しました: {age_val} 歳', 'profile': profile_obj})
        except Exception:
            return jsonify({'reply': '年齢は数字で指定してください（例: 年齢登録 30）'})

    # 地域登録コマンド: "地域登録 Tokyo"
    m_region_reg = re.match(r'地域登録\s+(.+)', message)
    if m_region_reg:
        region_val = m_region_reg.group(1).strip()
        if region_val:
            profile_obj['region'] = region_val
            return jsonify({'reply': f'地域を登録しました: {region_val}', 'profile': profile_obj})
        else:
            return jsonify({'reply': "地域登録 の後に地域名を入力してください（例: 地域登録 Tokyo）"})

    # スケジュール作成 (structured)
    if message.startswith('スケジュール作成'):
        data = payload.get('data') or {}
        title = data.get('title') or '無題'
        dt = data.get('datetime') or data.get('date') or ''
        items = data.get('items') or []
        location = data.get('location') or ''
        alarm = None
        status = data.get('status', 'active')
        
        # アラーム時刻の設定（オプション）
        if data.get('alarm'):
            try:
                alarm = datetime.fromisoformat(data['alarm'])
            except (ValueError, TypeError):
                pass

        if not dt:
            return jsonify({'reply': '日時を指定してください（例: 2025-10-30 14:00）'}), 400
        
        # 保存（UUIDを生成）
        schedule_id = str(uuid.uuid4())
        s = Schedule(
            id=schedule_id,
            title=title,
            datetime=dt,
            location=location,
            items_json=json.dumps(items, ensure_ascii=False),
            status=status,
            alarm=alarm
        )
        db.session.add(s)
        db.session.commit()
        
        return jsonify({
            'reply': f'スケジュールを作成しました: {title} @ {dt}' + (f'\nアラーム設定: {alarm.isoformat()}' if alarm else ''),
            'schedule': s.to_dict()
        })

    # 予定一覧
    if '予定' in message:
        now = datetime.now()
        # デフォルトで未完了（active）の予定のみを表示
        status_filter = 'active'

        # 「完了した予定」や「キャンセルした予定」のような指定を検出
        if '完了' in message or '済' in message:
            status_filter = 'completed'
        elif 'キャンセル' in message or '中止' in message:
            status_filter = 'cancelled'
        elif '全' in message or 'すべて' in message:
            status_filter = None  # すべての予定を表示

        # DBアクセスは例外保護して、テーブル未作成などのエラーを適切に扱う
        try:
            # クエリの構築
            query = Schedule.query
            if status_filter:
                query = query.filter(Schedule.status == status_filter)

            # 日付でのフィルタリング
            if '今日' in message:
                today = now.strftime('%Y-%m-%d')
                query = query.filter(Schedule.datetime.like(f'{today}%'))
            elif '今週' in message:
                # 簡易的な今週のフィルタリング（当日から7日間）
                next_week = (now + timedelta(days=7)).strftime('%Y-%m-%d')
                query = query.filter(
                    Schedule.datetime >= now.strftime('%Y-%m-%d'),
                    Schedule.datetime < next_week
                )

            # 並び順（デフォルトは日付順）
            query = query.order_by(Schedule.datetime)

            # 予定の取得（デフォルトで10件まで）
            schs = query.limit(10).all()
        except Exception as e:
            # テーブル未作成などの問題が起きた場合は予定がないものとして扱う
            print(f"データベースエラー: {e}")
            return jsonify({'reply': '予定はありません（データベースにアクセスできませんでした）。'})

        if not schs:
            status_msg = {
                'active': '未完了の',
                'completed': '完了した',
                'cancelled': 'キャンセルされた'
            }.get(status_filter, '')
            return jsonify({'reply': f'{status_msg}予定はありません。'})

        lines = []
        for s in schs:
            try:
                dt = datetime.fromisoformat(s.datetime)
                date_str = dt.strftime('%Y/%m/%d %H:%M')
            except ValueError:
                date_str = s.datetime

            status_mark = {
                'active': '⏳',
                'completed': '✅',
                'cancelled': '❌'
            }.get(s.status, '')

            line = f"{status_mark} {s.title} — {date_str}"
            if s.location:
                line += f" @ {s.location}"
            if s.alarm:
                line += f" 🔔"
            lines.append(line)

        # ステータスに応じたヘッダー
        header = {
            'active': '未完了の予定',
            'completed': '完了した予定',
            'cancelled': 'キャンセルされた予定',
            None: 'すべての予定'
        }.get(status_filter, '予定') + '一覧'

        return jsonify({
            'reply': f'{header}:\n' + '\n'.join(lines),
            'schedules': [s.to_dict() for s in schs]
        })

    # 次の予定（直近の未完了予定）
    if '次の予定' in message or message.strip() == '次の予定':
        try:
            sch = Schedule.query.filter(Schedule.status == 'active').order_by(Schedule.datetime).first()
        except Exception as e:
            print(f"DB error when fetching next schedule: {e}")
            sch = None
        if not sch:
            return jsonify({'reply': '直近の予定はありません。'})
        items = json.loads(sch.items_json) if sch.items_json else []
        when = sch.datetime
        reply = f'次の予定: {sch.title} — {when}'
        if sch.location:
            reply += f' @ {sch.location}'
        if items:
            reply += '\n持ち物: ' + ', '.join(items)
        return jsonify({'reply': reply, 'schedule': sch.to_dict()})

    # 食事照会（チャット）: 今日/昨日/直近/特定の日 or meal type 指定をサポート
    if '食事' in message or '朝ごはん' in message or '朝食' in message or '昼ごはん' in message or '昼食' in message or '夕食' in message or '最近の食事' in message or '直近の食事' in message:
        # 日付フィルタ
        date_filter = None
        if '今日' in message:
            date_filter = datetime.now().strftime('%Y-%m-%d')
        elif '昨日' in message:
            date_filter = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            # YYYY-MM-DD のような日付が含まれていれば抽出
            mdate = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', message)
            if mdate:
                date_filter = mdate.group(1)

        # 食事種別フィルタ
        meal_type = None
        if re.search(r'朝|朝ごはん|朝食', message):
            meal_type = '朝'
        elif re.search(r'昼|昼ごはん|昼食', message):
            meal_type = '昼'
        elif re.search(r'夕|夕食|夜', message):
            meal_type = '夕'

        try:
            query = Meal.query
            if date_filter:
                query = query.filter(Meal.date.like(f'{date_filter}%'))
            if meal_type:
                # meal_type は保存時に任意の文字列なので部分一致で検索
                query = query.filter(Meal.meal_type.like(f'%{meal_type}%'))
            ms = query.order_by(Meal.date.desc()).limit(10).all()
        except Exception as e:
            print(f"DB error when fetching meals: {e}")
            return jsonify({'reply': '食事記録はありません（データベースにアクセスできませんでした）。'})

        if not ms:
            return jsonify({'reply': '該当する食事記録はありません。'})

        lines = []
        for m in ms:
            lines.append(f"{m.date} — {m.meal_type} — {m.items or 'メニューなし'}" + (f" ({m.calories} kcal)" if m.calories else ''))
        return jsonify({'reply': '食事記録:\n' + '\n'.join(lines), 'meals': [m.to_dict() for m in ms]})

    # 忘れ物チェック（次の予定の持ち物を返す）
    if '忘れ物' in message:
        sch = Schedule.query.order_by(Schedule.datetime).first()
        if not sch:
            return jsonify({'reply': '直近の予定が見つかりません。'} )
        items = json.loads(sch.items_json) if sch.items_json else []
        if not items:
            return jsonify({'reply': f'直近の予定「{sch.title}」には持ち物が登録されていません。'} )
        return jsonify({'reply': f'直近の予定「{sch.title}」の持ち物: ' + ', '.join(items), 'items': items})

    # 服装提案（例: "服装 22"）
    if message.startswith('服装'):
        m = re.search(r"(-?\d+)", message)
        if not m:
            return jsonify({'reply': '気温を数字で指定してください（例: 服装 22）'}), 400
        temp = int(m.group(1))
        if temp >= 30:
            rec = 'とても暑いです。薄手の服、帽子、こまめな水分補給を。'
        elif temp >= 24:
            rec = '暑めです。半袖＋薄手の羽織が良いでしょう。'
        elif temp >= 18:
            rec = '快適な気温。長袖＋軽い上着が良いです。'
        elif temp >= 10:
            rec = '肌寒いです。ジャケットやセーターをおすすめします。'
        else:
            rec = 'かなり寒いです。コート、マフラー、手袋など暖かくしてください。'
        return jsonify({'reply': f'気温 {temp}°C の服装提案: {rec}'})

    # 天気問い合わせ（例: "東京の天気は"、"大阪の天気を教えて"、"今日の東京の天気は" など）
    # いくつかの自然表現パターンに対応する
    m_weather = None
    # パターン: 東京の天気 / 東京の天気は / 東京の天気を教えて / 東京の天気教えて
    for pat in [r'(.+?)の天気を教えて', r'(.+?)の天気教えて', r'(.+?)の天気は', r'今日の(.+?)の天気', r'(.+?)の天気']:
        m_weather = re.search(pat, message)
        if m_weather:
            break
    if m_weather:
        city = m_weather.group(1).strip()
        # 空文字や一般的すぎる語を弾く
        if city:
            result = get_current_weather(city)
            if result.get('error'):
                return jsonify({'reply': f'天気情報の取得に失敗しました: {result.get("error")}'})
            w = result.get('weather')
            if not w:
                return jsonify({'reply': '天気情報が見つかりませんでした。都市名を確認してください。'})
            reply = (f"{w.get('city')} の天気: {w.get('description')}。気温 {w.get('temp')}°C、体感 {w.get('feels_like')}°C、"
                     f"湿度 {w.get('humidity')}%、風速 {w.get('wind_speed')} m/s")
            return jsonify({'reply': reply, 'weather': w})

    # 「天気」という語を含むが都市指定がない場合は、プロフィールの地域を使う
    if '天気' in message:
        # 追加で表示したい地域が「～も」の形で与えられているかを探す
        extras = re.findall(r'([^\s、。,。？\?！!]+?)も', message)
        # ペイロードに profile が含まれている場合はそれを使う（クライアント側で送られた JSON）
        profile_payload = payload.get('profile')
        profile_region = None
        profile_display_name = None
        if isinstance(profile_payload, dict):
            profile_region = profile_payload.get('region')
            profile_display_name = profile_payload.get('nickname') or profile_payload.get('name')
        elif profile_payload:
            p = load_profile(profile_payload)
            if p:
                profile_region = p.get('region')
                profile_display_name = p.get('nickname') or p.get('name')

        cities = []
        # まずプロファイル地域を優先として追加
        if not m_weather and profile_region:
            cities.append(profile_region)
        # extras にある地域を追加（重複排除）
        for e in extras:
            e = e.strip()
            if e and e not in cities:
                cities.append(e)

        if not cities:
            # まだ地域が決まらない -> ユーザーに確認
            return jsonify({'reply': 'どの地域の天気を知りたいですか？（例: 東京の天気は）'})

        # 各地域について天気を取得してまとめて返す
        lines = []
        weathers = {}
        for c in cities:
            r = get_current_weather(c)
            if r.get('error'):
                lines.append(f"{c}: 取得失敗 ({r.get('error')})")
            else:
                w = r.get('weather')
                lines.append(f"{w.get('city')}: {w.get('description')}, {w.get('temp')}°C (体感 {w.get('feels_like')}°C)")
                weathers[c] = w
        prefix = ''
        if profile_region:
            prefix = f"プロファイル({profile_display_name})の地域を使用しています。\n"
        return jsonify({'reply': prefix + '\n'.join(lines), 'weathers': weathers})

    # 食事記録（structured）
    if message.startswith('食事記録'):
        data = payload.get('data') or {}
        meal_type = data.get('meal_type') or '不明'
        items = data.get('items') or ''
        calories = data.get('calories')
        photos = data.get('photos', [])
        rating = data.get('rating')
        notes = data.get('notes')

        # UUIDを生成
        meal_id = str(uuid.uuid4())
        m = Meal(
            id=meal_id,
            date=datetime.now().strftime('%Y-%m-%d %H:%M'),
            meal_type=meal_type,
            items=items,
            calories=calories,
            photos=json.dumps(photos) if photos else None,
            rating=rating,
            notes=notes
        )
        db.session.add(m)
        db.session.commit()

        reply = f'食事を記録しました: {meal_type} — {items}'
        if calories:
            reply += f' ({calories} kcal)'
        if rating:
            reply += f'\n評価: {"★" * rating}{"☆" * (5-rating)}'
        if notes:
            reply += f'\nメモ: {notes}'

        return jsonify({'reply': reply, 'meal': m.to_dict()})

    # 既定のヘルプ
    help_text = (
        '使い方（簡易）:\n'
        '・スケジュール作成（構造化）: メッセージに `スケジュール作成` とし、JSON の data を送ってください。\n'
        '・予定: 「予定」または「次の予定」と入力\n'
        '・忘れ物: 「忘れ物」と入力\n'
        '・服装: 「服装 22」のように気温を与える\n'
        '・食事記録: `食事記録` として data を送ってください\n'
    )
    return jsonify({'reply': help_text})


# --- API 単独エンドポイント（オプション） ---
@app.route('/api/schedules', methods=['GET', 'POST', 'PUT'])
def schedules_api():
    if request.method == 'POST':
        payload = request.get_json() or {}
        title = payload.get('title') or '無題'
        dt = payload.get('datetime')
        items = payload.get('items') or []
        location = payload.get('location')
        status = payload.get('status', 'active')
        alarm = None

        if payload.get('alarm'):
            try:
                alarm = datetime.fromisoformat(payload['alarm'])
            except (ValueError, TypeError):
                pass

        if not dt:
            return jsonify({'error': 'datetime required'}), 400

        schedule_id = str(uuid.uuid4())
        s = Schedule(
            id=schedule_id,
            title=title,
            datetime=dt,
            location=location,
            items_json=json.dumps(items, ensure_ascii=False),
            status=status,
            alarm=alarm
        )
        db.session.add(s)
        db.session.commit()
        return jsonify({'schedule': s.to_dict()})

    elif request.method == 'PUT':
        payload = request.get_json() or {}
        schedule_id = payload.get('id')
        if not schedule_id:
            return jsonify({'error': 'id required'}), 400

        s = Schedule.query.get(schedule_id)
        if not s:
            return jsonify({'error': 'schedule not found'}), 404

        # 更新可能なフィールド
        if 'title' in payload:
            s.title = payload['title']
        if 'datetime' in payload:
            s.datetime = payload['datetime']
        if 'location' in payload:
            s.location = payload['location']
        if 'items' in payload:
            s.items_json = json.dumps(payload['items'], ensure_ascii=False)
        if 'status' in payload:
            s.status = payload['status']
        if 'alarm' in payload:
            try:
                s.alarm = datetime.fromisoformat(payload['alarm']) if payload['alarm'] else None
            except (ValueError, TypeError):
                pass

        # updated_at は自動的に更新されます（onupdate=datetime.utcnow）
        db.session.commit()
        return jsonify({'schedule': s.to_dict()})

    else:
        # GETの場合、フィルター条件を受け付ける
        status = request.args.get('status')
        from_date = request.args.get('from')
        to_date = request.args.get('to')
        
        query = Schedule.query
        if status:
            query = query.filter(Schedule.status == status)
        if from_date:
            query = query.filter(Schedule.datetime >= from_date)
        if to_date:
            query = query.filter(Schedule.datetime <= to_date)
        
        schs = query.order_by(Schedule.datetime).all()
        return jsonify({'schedules': [s.to_dict() for s in schs]})


@app.route('/api/meals', methods=['GET', 'POST', 'PUT'])
def meals_api():
    if request.method == 'POST':
        payload = request.get_json() or {}
        meal_type = payload.get('meal_type') or '不明'
        items = payload.get('items') or ''
        calories = payload.get('calories')
        photos = payload.get('photos', [])
        rating = payload.get('rating')
        notes = payload.get('notes')

        meal_id = str(uuid.uuid4())
        m = Meal(
            id=meal_id,
            date=datetime.now().strftime('%Y-%m-%d %H:%M'),
            meal_type=meal_type,
            items=items,
            calories=calories,
            photos=json.dumps(photos) if photos else None,
            rating=rating,
            notes=notes
        )
        db.session.add(m)
        db.session.commit()
        return jsonify({'meal': m.to_dict()})

    elif request.method == 'PUT':
        payload = request.get_json() or {}
        meal_id = payload.get('id')
        if not meal_id:
            return jsonify({'error': 'id required'}), 400

        m = Meal.query.get(meal_id)
        if not m:
            return jsonify({'error': 'meal not found'}), 404

        # 更新可能なフィールド
        if 'meal_type' in payload:
            m.meal_type = payload['meal_type']
        if 'items' in payload:
            m.items = payload['items']
        if 'calories' in payload:
            m.calories = payload['calories']
        if 'photos' in payload:
            m.photos = json.dumps(payload['photos']) if payload['photos'] else None
        if 'rating' in payload:
            m.rating = payload['rating']
        if 'notes' in payload:
            m.notes = payload['notes']

        db.session.commit()
        return jsonify({'meal': m.to_dict()})

    else:
        # GETの場合、フィルター条件を受け付ける
        date = request.args.get('date')
        meal_type = request.args.get('meal_type')
        
        query = Meal.query
        if date:
            query = query.filter(Meal.date.like(f'{date}%'))
        if meal_type:
            query = query.filter(Meal.meal_type == meal_type)
        
        ms = query.order_by(Meal.date.desc()).limit(20).all()
        return jsonify({'meals': [m.to_dict() for m in ms]})


# --- 天気 API エンドポイント ---
@app.route('/api/weather', methods=['GET', 'POST'])
def weather_api():
    # GET の場合は query string から、POST の場合は JSON から city を受け取る
    city = None
    if request.method == 'GET':
        city = request.args.get('city')
    else:
        payload = request.get_json() or {}
        city = payload.get('city')
        
        # クライアントから送られたプロファイルをセッションに登録
        profile_payload = payload.get('profile')
        if profile_payload:
            if isinstance(profile_payload, dict):
                session['profile'] = profile_payload
            elif isinstance(profile_payload, str):
                # 文字列の場合はサーバーに保存されたプロファイル名として読み込む
                p = load_profile(profile_payload)
                if p:
                    session['profile'] = p
    
    # フロントが profile を送ってきた場合はプロフィールの region を利用する
    if not city:
        payload = request.get_json() or {}
        profile_name = payload.get('profile')
        if profile_name:
            p = load_profile(profile_name)
            if p and p.get('region'):
                city = p.get('region')
    if not city:
        return jsonify({'error': 'city parameter is required (例: ?city=Tokyo または {"city":"Tokyo"} )'}), 400
    result = get_current_weather(city)
    return jsonify(result)


@app.route('/api/assistant_call', methods=['POST'])
def assistant_call():
    """Generic function call entrypoint for external (Gemini) calls.
    Expect JSON: {"mode": int, "type": int, "data": object|string|null}
    mode: 1=profile, 2=schedule, 5=meal
    type: 1=add,2=modify,3=delete,4=read
    data: operation parameters (for add/modify/delete: full object; for delete: id string or {id:...}; for read: filter or null)
    """
    payload = request.get_json() or {}
    
    # クライアントから送られたプロファイルをセッションに登録
    profile_payload = payload.get('profile')
    if profile_payload:
        if isinstance(profile_payload, dict):
            session['profile'] = profile_payload
        elif isinstance(profile_payload, str):
            # 文字列の場合はサーバーに保存されたプロファイル名として読み込む
            p = load_profile(profile_payload)
            if p:
                session['profile'] = p
    
    try:
        mode = int(payload.get('mode'))
        typ = int(payload.get('type'))
    except Exception:
        return jsonify({'error': 'mode and type must be integers'}), 400

    data = payload.get('data')

    # PROFILE (mode==1)
    if mode == 1:
        # READ
        if typ == 4:
            if not data:
                # セッション内プロファイルを取得
                prof = session.get('profile')
                # セッション内が空なら、外部ファイル（全プロファイル）から最初の1件を読み込む
                if not prof:
                    profiles = list_profiles()
                    prof = profiles[0] if profiles else None
                return jsonify({'profile': prof})
            # data に nickname が指定されていれば外部ファイルから読み込む
            nickname = data if isinstance(data, str) else data.get('nickname')
            if not nickname:
                # data が指定されていても nickname がない場合はセッション内を返す
                prof = session.get('profile')
                # セッション内が空なら、外部ファイルから最初の1件を読み込む
                if not prof:
                    profiles = list_profiles()
                    prof = profiles[0] if profiles else None
                return jsonify({'profile': prof})
            # 外部ファイルから読み込む
            p = load_profile(nickname)
            return jsonify({'profile': p})

        # ADD - セッション内プロファイルを全て置換
        if typ == 1:
            if not isinstance(data, dict):
                return jsonify({'error': 'profile data (object) required for add'}), 400
            # 前のセッション内プロファイルを保存（undo 用）
            prev = session.get('profile', {})
            # セッション内プロファイルを新しいデータで置換
            session['profile'] = data
            inverse = {'op': 'update', 'mode': 1, 'data': prev} if prev else {'op': 'delete', 'mode': 1, 'data': None}
            _record_action(1, 1, data, inverse)
            return jsonify({'ok': True, 'profile': data})

        # MODIFY - セッション内プロファイルの個別要素を更新
        if typ == 2:
            if not isinstance(data, dict):
                return jsonify({'error': 'profile data (object) required for modify'}), 400
            prev = session.get('profile', {})
            if not prev:
                return jsonify({'error': 'no profile in session; use type=1 (add) first'}), 400
            # 指定フィールドのみ更新
            updated = prev.copy()
            updated.update(data)
            session['profile'] = updated
            inverse = {'op': 'update', 'mode': 1, 'data': prev}
            _record_action(1, 2, data, inverse)
            return jsonify({'ok': True, 'profile': updated})

        # DELETE - セッション内プロファイルをクリア
        if typ == 3:
            prev = session.get('profile', {})
            session.pop('profile', None)
            inverse = {'op': 'add', 'mode': 1, 'data': prev} if prev else None
            _record_action(1, 3, None, inverse)
            return jsonify({'ok': True})

        return jsonify({'error': 'unsupported profile operation'}), 400

    # SCHEDULE (mode==2)
    if mode == 2:
        # READ
        if typ == 4:
            # if data provided and contains id, return that schedule, else all
            if data and isinstance(data, dict) and data.get('id'):
                s = Schedule.query.get(data.get('id'))
                return jsonify({'schedule': s.to_dict() if s else None})
            schs = Schedule.query.order_by(Schedule.datetime).all()
            return jsonify({'schedules': [s.to_dict() for s in schs]})

        # ADD
        if typ == 1:
            if not isinstance(data, dict):
                return jsonify({'error': 'schedule data required for add'}), 400
            sid = str(uuid.uuid4())
            s = Schedule(
                id=sid,
                title=data.get('title',''),
                datetime=data.get('datetime',''),
                location=data.get('location'),
                items_json=json.dumps(data.get('items',[]), ensure_ascii=False),
                status=data.get('status','active'),
                alarm=datetime.fromisoformat(data['alarm']) if data.get('alarm') else None
            )
            db.session.add(s)
            db.session.commit()
            inverse = {'op':'delete','mode':2,'data': {'id': sid}}
            _record_action(2,1,data, inverse)
            return jsonify({'ok': True, 'schedule': s.to_dict()})

        # MODIFY
        if typ == 2:
            if not isinstance(data, dict) or not data.get('id'):
                return jsonify({'error': 'schedule id and data required for modify'}), 400
            s = Schedule.query.get(data.get('id'))
            if not s:
                return jsonify({'error': 'schedule not found'}), 404
            prev = s.to_dict()
            # update allowed fields
            for f in ('title','datetime','location','status'):
                if f in data:
                    setattr(s,f,data.get(f))
            if 'items' in data:
                s.items_json = json.dumps(data.get('items',[]), ensure_ascii=False)
            if 'alarm' in data:
                try:
                    s.alarm = datetime.fromisoformat(data['alarm']) if data['alarm'] else None
                except Exception:
                    pass
            db.session.commit()
            inverse = {'op':'update','mode':2,'data': prev}
            _record_action(2,2,data,inverse)
            return jsonify({'ok': True, 'schedule': s.to_dict()})

        # DELETE
        if typ == 3:
            sid = data if isinstance(data, str) else (data.get('id') if isinstance(data, dict) else None)
            if not sid:
                return jsonify({'error': 'schedule id required for delete'}), 400
            s = Schedule.query.get(sid)
            if not s:
                return jsonify({'error': 'schedule not found'}), 404
            prev = s.to_dict()
            db.session.delete(s)
            db.session.commit()
            inverse = {'op':'add','mode':2,'data': prev}
            _record_action(2,3,{'id':sid}, inverse)
            return jsonify({'ok': True})

        return jsonify({'error': 'unsupported schedule operation'}), 400

    # MEAL (mode==5)
    if mode == 5:
        if typ == 4:
            if data and isinstance(data, dict) and data.get('id'):
                m = Meal.query.get(data.get('id'))
                return jsonify({'meal': m.to_dict() if m else None})
            ms = Meal.query.order_by(Meal.date.desc()).all()
            return jsonify({'meals': [m.to_dict() for m in ms]})

        if typ == 1:
            if not isinstance(data, dict):
                return jsonify({'error': 'meal data required for add'}), 400
            mid = str(uuid.uuid4())
            m = Meal(
                id=mid,
                date=data.get('date') or datetime.now().strftime('%Y-%m-%d %H:%M'),
                meal_type=data.get('meal_type','不明'),
                items=data.get('items',''),
                calories=data.get('calories'),
                photos=json.dumps(data.get('photos')) if data.get('photos') else None,
                rating=data.get('rating'),
                notes=data.get('notes')
            )
            db.session.add(m)
            db.session.commit()
            inverse = {'op':'delete','mode':5,'data': {'id': mid}}
            _record_action(5,1,data,inverse)
            return jsonify({'ok': True, 'meal': m.to_dict()})

        if typ == 2:
            if not isinstance(data, dict) or not data.get('id'):
                return jsonify({'error': 'meal id and data required for modify'}), 400
            m = Meal.query.get(data.get('id'))
            if not m:
                return jsonify({'error': 'meal not found'}), 404
            prev = m.to_dict()
            for f in ('meal_type','items','calories','rating','notes'):
                if f in data:
                    setattr(m,f,data.get(f))
            if 'photos' in data:
                m.photos = json.dumps(data.get('photos')) if data.get('photos') else None
            db.session.commit()
            inverse = {'op':'update','mode':5,'data': prev}
            _record_action(5,2,data,inverse)
            return jsonify({'ok': True, 'meal': m.to_dict()})

        if typ == 3:
            mid = data if isinstance(data, str) else (data.get('id') if isinstance(data, dict) else None)
            if not mid:
                return jsonify({'error': 'meal id required for delete'}), 400
            m = Meal.query.get(mid)
            if not m:
                return jsonify({'error': 'meal not found'}), 404
            prev = m.to_dict()
            db.session.delete(m)
            db.session.commit()
            inverse = {'op':'add','mode':5,'data': prev}
            _record_action(5,3,{'id':mid}, inverse)
            return jsonify({'ok': True})

        return jsonify({'error': 'unsupported meal operation'}), 400

    return jsonify({'error': f'unsupported mode: {mode}'}), 400


@app.route('/api/assistant_undo', methods=['POST'])
def assistant_undo():
    """Undo the last logged action. Accepts optional JSON {mode: int} to restrict undo to a mode."""
    payload = request.get_json() or {}
    mode = payload.get('mode')
    try:
        q = ActionLog.query.filter(ActionLog.undone == False)
        if mode:
            q = q.filter(ActionLog.mode == int(mode))
        last = q.order_by(ActionLog.created_at.desc()).first()
        if not last:
            return jsonify({'error': 'no action to undo'}), 404
        inv = json.loads(last.inverse) if last.inverse else None
        if not inv:
            return jsonify({'error': 'no inverse available for last action'}), 400
        res = _apply_inverse(inv)
        last.undone = True
        db.session.commit()
        return jsonify({'ok': True, 'result': res, 'action': last.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/time', methods=['GET'])
def time_api():
    """現在時刻を返すエンドポイント。NTP サーバから取得を試み、失敗したらシステム時刻を返す。"""
    server = request.args.get('server') or get_ntp_server()
    try:
        t = get_ntp_time(server)
        return jsonify({'source': 'ntp', 'server': server, 'utc': t.get('utc'), 'local': t.get('local')})
    except Exception as e:
        # フォールバックでシステム時刻を返す
        utc = datetime.utcnow().isoformat()
        local = datetime.now().isoformat()
        return jsonify({'source': 'system', 'error': str(e), 'utc': utc, 'local': local})


# --- Profiles API ---
@app.route('/api/profiles', methods=['GET', 'POST'])
def profiles_api():
    # サーバー側でのプロファイル永続化は行いません。クライアント側でのインポート/エクスポートを利用してください。
    if request.method == 'GET':
        return jsonify({'profiles': []})
    else:
        return jsonify({'error': 'サーバー側でのプロファイル保存はサポートしていません。クライアントで管理してください。'}), 403


@app.route('/api/profiles/import', methods=['POST'])
def profiles_import():
    # サーバー側でのインポート（保存）はサポートしません。
    return jsonify({'error': 'サーバー側でのプロファイル保存はサポートしていません。クライアントで管理してください。'}), 403


@app.route('/api/profiles/export', methods=['GET'])
def profiles_export():
    # サーバー側でのエクスポートはサポートしません。プロファイルはクライアントで管理してください。
    return jsonify({'error': 'サーバー側でのプロファイルエクスポートはサポートしていません。クライアントで管理してください。'}), 403


if __name__ == '__main__':
    # データベース初期化はアプリケーションコンテキスト内で実行する
    with app.app_context():
        try:
            # 強制的にテーブルを作成（存在しない場合のみ）
            db.create_all()
            init_db()
            print("データベースの初期化が完了しました。")
        except Exception as e:
            print(f"データベース初期化エラー: {str(e)}")
            exit(1)
    app.run(debug=True)
