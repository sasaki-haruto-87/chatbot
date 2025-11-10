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

async function sendMessage(message, data){
  addMessage('user', message);
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message, data})
  });
  const j = await res.json();
  addMessage('bot', j.reply || JSON.stringify(j));
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
