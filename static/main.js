const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');

function addMessage(author, text){
  const el = document.createElement('div');
  el.className = 'message ' + (author === 'user' ? 'user' : 'bot');
  el.textContent = (author === 'user' ? 'あなた: ' : '秘書: ') + text;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function clearChat() {
  chatEl.innerHTML = '';
  addMessage('bot', 'チャット履歴をクリアしました。');
}

async function sendMessage(message, data){
  // チャットクリアのコマンドをチェック
  if(message.toLowerCase() === 'clear' || message === 'クリア' || message === '履歴削除') {
    clearChat();
    return;
  }

  addMessage('user', message);
  // 送信時に現在のプロファイル情報（クライアント側に保持している JSON）を付与
  const profileRaw = localStorage.getItem('profileData') || null;
  const profileObj = profileRaw ? JSON.parse(profileRaw) : null;
  const body = {message, data};
  if(profileObj) body.profile = profileObj;
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const j = await res.json();
  addMessage('bot', j.reply || JSON.stringify(j));
  // サーバーが profile を返したらクライアント側に保存（ダウンロード前の作業領域として）
  if(j.profile){
    localStorage.setItem('profileData', JSON.stringify(j.profile));
    addMessage('bot', `プロファイルを更新しました: ${j.profile.nickname || j.profile.name || ''}`);
  }
}

sendBtn.addEventListener('click', ()=>{
  const m = inputEl.value.trim();
  if(!m) return;
  sendMessage(m);
  inputEl.value = '';
});

inputEl.addEventListener('keypress', (e)=>{
  if(e.key === 'Enter') sendBtn.click();
});

// スケジュールフォーム
const scheduleForm = document.getElementById('scheduleForm');
scheduleForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const title = document.getElementById('sch_title').value || '無題';
  const datetime = document.getElementById('sch_datetime').value;
  const items = (document.getElementById('sch_items').value || '').split(',').map(s=>s.trim()).filter(Boolean);
  if(!datetime){ alert('日時を入力してください'); return; }
  await sendMessage('スケジュール作成', {title, datetime, items});
  scheduleForm.reset();
});

// 食事フォーム
const mealForm = document.getElementById('mealForm');
mealForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const meal_type = document.getElementById('meal_type').value || '食事';
  const items = document.getElementById('meal_items').value || '';
  const calories = parseInt(document.getElementById('meal_cal').value) || null;
  await sendMessage('食事記録', {meal_type, items, calories});
  mealForm.reset();
});

// 天気取得
const getWeatherBtn = document.getElementById('getWeather');
if(getWeatherBtn){
  getWeatherBtn.addEventListener('click', async ()=>{
    const city = document.getElementById('weather_city').value.trim();
    const resDiv = document.getElementById('weatherResult');
    if(!city){ alert('都市名を入力してください'); return; }
    resDiv.textContent = '取得中...';
    try{
      const profileRaw = localStorage.getItem('profileData') || null;
      const profileObj = profileRaw ? JSON.parse(profileRaw) : null;
      const payload = {city};
      if(profileObj) payload.profile = profileObj;
      const res = await fetch('/api/weather', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const j = await res.json();
      if(j.error){
        resDiv.textContent = 'エラー: ' + j.error;
        addMessage('bot', '天気取得エラー: ' + j.error);
        return;
      }
      const w = j.weather;
      if(!w){ resDiv.textContent = '天気情報が見つかりません。'; return; }
      const html = `都市: ${w.city}\n天気: ${w.description}\n気温: ${w.temp} °C (体感 ${w.feels_like} °C)\n湿度: ${w.humidity}%\n風速: ${w.wind_speed} m/s`;
      // 表示
      resDiv.textContent = html;
      addMessage('bot', `天気情報: ${w.city} — ${w.description}, ${w.temp}°C`);
    }catch(err){
      resDiv.textContent = 'エラーが発生しました: ' + err;
      addMessage('bot', '天気取得中にエラーが発生しました');
    }
  });
}

// ページを開いたときは、もし以前読み込んでいたプロファイルがあれば保持して読み込む
// （ユーザーが以前ページで読み込んだ profile JSON があれば次回も利用できるようにする）
const existingProfileRaw = localStorage.getItem('profileData');
if(existingProfileRaw){
  try{
    const p = JSON.parse(existingProfileRaw);
    addMessage('bot', '前回のプロファイルを読み込みました: ' + (p.nickname || p.name || ''));
  }catch(e){
    // 不正な JSON は破棄
    localStorage.removeItem('profileData');
  }
}

// トップのプロファイル保存/読み込みボタン
const saveProfileTop = document.getElementById('saveProfileTop');
const loadProfileTop = document.getElementById('loadProfileTop');
const loadProfileFileTop = document.getElementById('loadProfileFileTop');

if(saveProfileTop){
  saveProfileTop.addEventListener('click', ()=>{
    const raw = localStorage.getItem('profileData');
    if(!raw){ alert('保存するプロファイルがありません（チャットで属性を設定してください）'); return; }
    const p = JSON.parse(raw);
    const blob = new Blob([JSON.stringify(p, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = (p.nickname || 'profile') + '.json';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  });
}

if(loadProfileTop && loadProfileFileTop){
  loadProfileTop.addEventListener('click', ()=> loadProfileFileTop.click());
  loadProfileFileTop.addEventListener('change', async (e)=>{
    const f = e.target.files[0];
    if(!f) return;
    try{
      const txt = await f.text();
      const p = JSON.parse(txt);
      // クライアント側の作業領域に保存
      localStorage.setItem('profileData', JSON.stringify(p));
      addMessage('bot', 'プロファイルを読み込みました: ' + (p.nickname || p.name || ''));
    }catch(err){ alert('JSON 読み込みに失敗しました: ' + err); }
    // reset input
    loadProfileFileTop.value = null;
  });
}

// --- 現在時刻の取得表示 ---
const currentTimeEl = document.getElementById('currentTime');
const refreshTimeBtn = document.getElementById('refreshTime');

let _clockInterval = null;
let _serverOffsetMs = 0; // server_time_ms - Date.now()

function _formatDateJP(d){
  // 日本語ロケールで短めに表示
  try{
    return d.toLocaleString('ja-JP');
  }catch(e){
    return d.toString();
  }
}

function _startClock(initialIso){
  // 既存のインターバルがあればクリア
  if(_clockInterval) clearInterval(_clockInterval);
  let serverMs = Date.parse(initialIso);
  if(isNaN(serverMs)) serverMs = Date.now();
  _serverOffsetMs = serverMs - Date.now();

  function update(){
    const nowMs = Date.now() + _serverOffsetMs;
    const d = new Date(nowMs);
    if(currentTimeEl) currentTimeEl.textContent = _formatDateJP(d);
  }

  update();
  _clockInterval = setInterval(update, 1000);
}

async function fetchTime(){
  if(!currentTimeEl) return;
  try{
    const res = await fetch('/api/time');
    const j = await res.json();
    // j.local は ISO 文字列 (fallback あり)
    if(j && j.local){
      _startClock(j.local);
    }else{
      // フォールバック
      _startClock(new Date().toISOString());
    }
  }catch(err){
    // 取得失敗時はローカル時刻で開始
    _startClock(new Date().toISOString());
  }
}

if(refreshTimeBtn){
  refreshTimeBtn.addEventListener('click', fetchTime);
}

// 初回ロード時に時刻を取得してリアルタイム表示開始
fetchTime();
