import os
import json
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

# Optional provider clients
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'assistant.db')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# --- Models ---
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    datetime = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    items_json = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'datetime': self.datetime,
            'location': self.location,
            'items': json.loads(self.items_json) if self.items_json else []
        }


class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(50), nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)
    items = db.Column(db.Text, nullable=True)
    calories = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'meal_type': self.meal_type,
            'items': self.items,
            'calories': self.calories
        }


# --- Helpers ---


def parse_time(time_str):
    try:
        return datetime.strptime(time_str, "%H:%M")
    except Exception:
        return None


def format_time(dt):
    return dt.strftime("%H:%M")


def generate_schedule_prompt(wake_up_time, departure_time, tasks):
    prompt = f"""あなたは効率的な秘書です。以下の条件に基づいて、起床から出発までの分刻みのスケジュールを作成してください。

条件:
- 起床時刻: {wake_up_time}
- 出発時刻: {departure_time}

タスク一覧:
"""
    for task in tasks:
        duration = task.get('duration', '0')
        priority = task.get('priority', '3')
        prompt += f"- {task['title']} (所要時間: {duration}分, 優先度: {priority})\\n"

    prompt += """
出力形式:
- JSON 形式で {"schedule": [...], "warnings": [...]} を返してください。
- 各予定は {"start":"HH:MM","end":"HH:MM","title":"...","reason":"..."} の形にしてください。

注意:
- 出発時刻は必ず守ること
- タスク間に5分程度の余裕を入れてください
"""
    return prompt


def generate_local_schedule(wake_up_time, departure_time, tasks):
    start = parse_time(wake_up_time)
    end = parse_time(departure_time)
    if not start or not end or end <= start:
        return {'schedule': [], 'warnings': ['時刻のパースに失敗しました（起床/出発時刻を確認してください）']}

    tasks_sorted = sorted(tasks, key=lambda t: (-int(t.get('priority', 3)), int(t.get('duration', 0))))

    schedule = []
    cur = start
    buffer_min = 5

    schedule.append({'start': format_time(cur), 'end': format_time(cur + timedelta(minutes=1)), 'title': '起床', 'reason': '一日の開始'})
    cur = cur + timedelta(minutes=1 + buffer_min)

    for t in tasks_sorted:
        dur = int(t.get('duration', 0))
        if dur <= 0:
            continue
        if cur + timedelta(minutes=dur) > end:
            continue
        item_start = cur
        item_end = cur + timedelta(minutes=dur)
        schedule.append({'start': format_time(item_start), 'end': format_time(item_end), 'title': t.get('title', 'タスク'), 'reason': 'ユーザー指定のタスク'})
        cur = item_end + timedelta(minutes=buffer_min)

    warnings = []
    if schedule and parse_time(schedule[-1]['end']) > end:
        warnings.append('タスクが出発時刻に間に合いませんでした。')

    return {'schedule': schedule, 'warnings': warnings}


def generate_local_schedule_from_prompt(prompt_text):
    wake = None
    depart = None
    tasks = []
    for line in prompt_text.splitlines():
        line = line.strip()
        if '起床時刻' in line and ':' in line:
            parts = line.split(':')
            wake = parts[-1].strip()
        if '出発時刻' in line and ':' in line:
            parts = line.split(':')
            depart = parts[-1].strip()
        if line.startswith('- '):
            m = line[2:]
            title = m.split('(')[0].strip()
            dur = 0
            pri = 3
            mm = re.search(r'所要時間:\s*(\d+)', m)
            if mm:
                dur = int(mm.group(1))
            pm = re.search(r'優先度:\s*(\d+)', m)
            if pm:
                pri = int(pm.group(1))
            if title:
                tasks.append({'title': title, 'duration': dur, 'priority': pri})
    if not wake or not depart:
        return {'schedule': [], 'warnings': ['ローカル解析で時刻が見つかりませんでした']}
    return generate_local_schedule(wake, depart, tasks)


# --- Provider wrapper ---
client = None


def init_openai_client():
    global client
    if client is not None:
        return
    if OpenAI is None:
        client = None
        return
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            client = OpenAI(api_key=api_key)
        else:
            client = OpenAI()
    except Exception as e:
        print('OpenAI init error:', repr(e))
        client = None


def init_gemini_client():
    if genai is None:
        return False
    api_key = os.getenv('GOOGLE_API_KEY')
    try:
        if api_key:
            genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print('Gemini init error:', repr(e))
        return False


def call_model(prompt):
    provider = os.getenv('PROVIDER', 'openai').lower()
    system = 'あなたは効率的なスケジュール管理の専門家です。'

    if provider in ('openai', 'open ai'):
        init_openai_client()
        if client is None:
            raise RuntimeError('OpenAI client not available')
        model = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=int(os.getenv('OPENAI_MAX_TOKENS', '800')),
            temperature=float(os.getenv('OPENAI_TEMP', '0.7'))
        )
        return resp.choices[0].message.content

    if provider in ('gemini', 'google', 'gcp'):
        if genai is None:
            raise RuntimeError('google.generativeai not installed')
        ok = init_gemini_client()
        if not ok:
            raise RuntimeError('Failed to init Gemini client')
        model = os.getenv('GOOGLE_MODEL', 'gemini-pro')
        # Ensure model name has proper prefix for Gemini API
        if not model.startswith('models/') and not model.startswith('tunedModels/'):
            model = f'models/{model}'
        
        temp = float(os.getenv('GOOGLE_TEMP', '0.7'))
        max_tokens = int(os.getenv('GOOGLE_MAX_OUTPUT_TOKENS', '800'))

        # Gemini API uses different message format; use simple prompt-based approach
        full_prompt = f"{system}\n\n{prompt}"
        
        # Try multiple calling styles to be tolerant of different genai versions
        resp = None
        try:
            # Preferred: genai.chat.create(...) - for newer SDK
            if hasattr(genai, 'chat') and hasattr(genai.chat, 'create'):
                resp = genai.chat.create(
                    model=model,
                    prompt=full_prompt,
                    temperature=temp,
                    max_output_tokens=max_tokens
                )
            # Some versions expose genai.chat as a callable function
            elif hasattr(genai, 'chat') and callable(genai.chat):
                # Try with max_output_tokens first
                try:
                    resp = genai.chat(
                        prompt=full_prompt,
                        temperature=temp,
                        max_output_tokens=max_tokens
                    )
                except TypeError:
                    # Fallback: try without max_output_tokens
                    resp = genai.chat(
                        prompt=full_prompt,
                        temperature=temp
                    )
            # Try genai.generate_text (older API)
            elif hasattr(genai, 'generate_text'):
                try:
                    resp = genai.generate_text(
                        prompt=full_prompt,
                        temperature=temp,
                        max_output_tokens=max_tokens
                    )
                except TypeError:
                    resp = genai.generate_text(
                        prompt=full_prompt,
                        temperature=temp
                    )
            elif hasattr(genai, 'generate'):
                # generic generate API
                try:
                    resp = genai.generate(
                        model=model,
                        prompt=full_prompt,
                        temperature=temp,
                        max_output_tokens=max_tokens
                    )
                except TypeError:
                    resp = genai.generate(
                        model=model,
                        prompt=full_prompt,
                        temperature=temp
                    )
            else:
                raise RuntimeError('Unsupported google.generativeai API surface')
        except AttributeError as e:
            # Surface mismatch
            raise RuntimeError(f'Gemini API attribute error: {e}')
        except Exception as e:
            # Pass through other exceptions
            raise

        # Normalize response: check for common shapes
        try:
            # object with candidates list
            if hasattr(resp, 'candidates') and resp.candidates:
                first = resp.candidates[0]
                # candidate may have .content or .text or .output
                content = getattr(first, 'content', None) or getattr(first, 'text', None) or getattr(first, 'output', None)
                if content:
                    return str(content)
            # Some responses have .result
            if hasattr(resp, 'result'):
                return str(getattr(resp, 'result'))
            # Try .text directly
            if hasattr(resp, 'text'):
                return str(getattr(resp, 'text'))
            # dict-like
            if isinstance(resp, dict):
                # common key names
                if 'candidates' in resp and resp['candidates']:
                    c = resp['candidates'][0]
                    if isinstance(c, dict):
                        return c.get('content') or c.get('text') or str(c)
                if 'output' in resp:
                    return json.dumps(resp['output'], ensure_ascii=False)
                if 'text' in resp:
                    return resp['text']
                if 'result' in resp:
                    return str(resp['result'])
                return str(resp)
            # Fallback: try string representation
        except Exception:
            pass

        return str(resp)

    if provider in ('hf', 'huggingface'):
        hf_key = os.getenv('HF_API_KEY')
        hf_model = os.getenv('HF_MODEL')
        if not hf_key or not hf_model:
            raise RuntimeError('HF_API_KEY or HF_MODEL not set')
        url = f'https://api-inference.huggingface.co/models/{hf_model}'
        headers = {"Authorization": f"Bearer {hf_key}"}
        payload = {"inputs": prompt, "options": {"wait_for_model": True}}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        j = r.json()
        if isinstance(j, list) and j and isinstance(j[0], dict) and 'generated_text' in j[0]:
            return j[0]['generated_text']
        if isinstance(j, dict):
            return j.get('generated_text') or j.get('text') or str(j)
        return str(j)

    if provider == 'local':
        return json.dumps(generate_local_schedule_from_prompt(prompt))

    raise RuntimeError(f'Unsupported provider: {provider}')


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/generate_schedule', methods=['POST'])
def generate_schedule():
    data = request.get_json() or {}
    wake_up_time = data.get('wakeUpTime')
    departure_time = data.get('departureTime')
    tasks = data.get('tasks', [])

    if not wake_up_time or not departure_time:
        return jsonify({'error': '起床時刻と出発時刻は必須です'}), 400

    prompt = generate_schedule_prompt(wake_up_time, departure_time, tasks)

    try:
        text = call_model(prompt)
        try:
            schedule_data = json.loads(text)
            return jsonify(schedule_data)
        except Exception:
            m = re.search(r"\{\s*\"schedule\"[\s\S]*\}", text)
            if m:
                try:
                    return jsonify(json.loads(m.group(0)))
                except Exception:
                    pass
            return jsonify({'error': 'スケジュールの生成に失敗しました', 'raw_response': text}), 500

    except Exception as e:
        err = str(e)
        # Gemini/API エラーの場合は詳しくログしてローカルフォールバックを試行
        print(f'Model error: {err}')
        # 404, 401, 429, quota エラーなど、外部API不可の場合はローカル生成
        if any(keyword in err.lower() for keyword in ['404', '401', '403', '429', 'quota', 'not found', 'unauthorized', 'permission', 'invalid', 'unsupported']):
            fallback = generate_local_schedule(wake_up_time, departure_time, tasks)
            if 'warnings' not in fallback:
                fallback['warnings'] = []
            fallback['warnings'].insert(0, f'外部モデルの利用不可のためローカルで生成しました: {err}')
            return jsonify(fallback)
        return jsonify({'error': f'モデル呼び出しエラー: {err}'}), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    payload = request.get_json() or {}
    message = (payload.get('message') or '').strip()

    if message.startswith('スケジュール作成'):
        data = payload.get('data') or {}
        title = data.get('title') or '無題'
        dt = data.get('datetime') or data.get('date') or ''
        items = data.get('items') or []
        location = data.get('location') or ''
        if not dt:
            return jsonify({'reply': '日時を指定してください（例: 2025-10-30 14:00）'}), 400
        s = Schedule(title=title, datetime=dt, location=location, items_json=json.dumps(items, ensure_ascii=False))
        db.session.add(s)
        db.session.commit()
        return jsonify({'reply': f'スケジュールを作成しました: {title} @ {dt}', 'schedule': s.to_dict()})

    if '予定' in message:
        schs = Schedule.query.order_by(Schedule.datetime).limit(10).all()
        if not schs:
            return jsonify({'reply': '予定はありません。'})
        lines = [f"{s.title} — {s.datetime}" for s in schs]
        return jsonify({'reply': '予定一覧:\n' + '\n'.join(lines), 'schedules': [s.to_dict() for s in schs]})

    if '忘れ物' in message:
        sch = Schedule.query.order_by(Schedule.datetime).first()
        if not sch:
            return jsonify({'reply': '直近の予定が見つかりません。'})
        items = json.loads(sch.items_json) if sch.items_json else []
        if not items:
            return jsonify({'reply': f'直近の予定「{sch.title}」には持ち物が登録されていません。'})
        return jsonify({'reply': f'直近の予定「{sch.title}」の持ち物: ' + ', '.join(items), 'items': items})

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

    if message.startswith('食事記録'):
        data = payload.get('data') or {}
        meal_type = data.get('meal_type') or '不明'
        items = data.get('items') or ''
        calories = data.get('calories')
        m = Meal(date=datetime.now().strftime('%Y-%m-%d %H:%M'), meal_type=meal_type, items=items, calories=calories)
        db.session.add(m)
        db.session.commit()
        return jsonify({'reply': f'食事を記録しました: {meal_type} — {items} ({calories or "不明"} kcal)', 'meal': m.to_dict()})

    help_text = (
        '使い方（簡易）:\n'
        '・スケジュール作成（構造化）: メッセージに `スケジュール作成` とし、JSON の data を送ってください。\n'
        '・予定: 「予定」または「次の予定」と入力\n'
        '・忘れ物: 「忘れ物」と入力\n'
        '・服装: 「服装 22」のように気温を与える\n'
        '・食事記録: `食事記録` として data を送ってください\n'
    )
    return jsonify({'reply': help_text})


@app.route('/api/schedules', methods=['GET', 'POST'])
def schedules_api():
    if request.method == 'POST':
        payload = request.get_json() or {}
        title = payload.get('title') or '無題'
        dt = payload.get('datetime')
        items = payload.get('items') or []
        if not dt:
            return jsonify({'error': 'datetime required'}), 400
        s = Schedule(title=title, datetime=dt, items_json=json.dumps(items, ensure_ascii=False))
        db.session.add(s)
        db.session.commit()
        return jsonify({'schedule': s.to_dict()})
    else:
        schs = Schedule.query.order_by(Schedule.datetime).all()
        return jsonify({'schedules': [s.to_dict() for s in schs]})


@app.route('/api/meals', methods=['GET', 'POST'])
def meals_api():
    if request.method == 'POST':
        payload = request.get_json() or {}
        meal_type = payload.get('meal_type') or '不明'
        items = payload.get('items') or ''
        calories = payload.get('calories')
        m = Meal(date=datetime.now().strftime('%Y-%m-%d %H:%M'), meal_type=meal_type, items=items, calories=calories)
        db.session.add(m)
        db.session.commit()
        return jsonify({'meal': m.to_dict()})
    else:
        ms = Meal.query.order_by(Meal.date.desc()).limit(20).all()
        return jsonify({'meals': [m.to_dict() for m in ms]})


if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(DB_PATH):
            db.create_all()
    app.run(debug=True)

