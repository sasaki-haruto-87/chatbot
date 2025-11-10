import os
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy

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
    datetime = db.Column(db.String(100), nullable=False)  # ISO string
    location = db.Column(db.String(200), nullable=True)
    items_json = db.Column(db.Text, nullable=True)  # JSON list of items

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
def init_db():
    if not os.path.exists(DB_PATH):
        db.create_all()


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    payload = request.get_json() or {}
    message = (payload.get('message') or '').strip()

    # スケジュール作成 (structured)
    if message.startswith('スケジュール作成'):
        data = payload.get('data') or {}
        title = data.get('title') or '無題'
        dt = data.get('datetime') or data.get('date') or ''
        items = data.get('items') or []
        location = data.get('location') or ''
        if not dt:
            return jsonify({'reply': '日時を指定してください（例: 2025-10-30 14:00）'}), 400
        # 保存
        s = Schedule(title=title, datetime=dt, location=location, items_json=json.dumps(items, ensure_ascii=False))
        db.session.add(s)
        db.session.commit()
        return jsonify({'reply': f'スケジュールを作成しました: {title} @ {dt}', 'schedule': s.to_dict()})

    # 予定一覧
    if '予定' in message:
        now = datetime.now()
        schs = Schedule.query.order_by(Schedule.datetime).limit(10).all()
        if not schs:
            return jsonify({'reply': '予定はありません。'} )
        lines = []
        for s in schs:
            lines.append(f"{s.title} — {s.datetime}")
        return jsonify({'reply': '予定一覧:\n' + '\n'.join(lines), 'schedules': [s.to_dict() for s in schs]})

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

    # 食事記録（structured）
    if message.startswith('食事記録'):
        data = payload.get('data') or {}
        meal_type = data.get('meal_type') or '不明'
        items = data.get('items') or ''
        calories = data.get('calories')
        m = Meal(date=datetime.now().strftime('%Y-%m-%d %H:%M'), meal_type=meal_type, items=items, calories=calories)
        db.session.add(m)
        db.session.commit()
        return jsonify({'reply': f'食事を記録しました: {meal_type} — {items} ({calories or "不明"} kcal)', 'meal': m.to_dict()})

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
    # データベース初期化はアプリケーションコンテキスト内で実行する
    with app.app_context():
        init_db()
    app.run(debug=True)
