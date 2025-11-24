// --- プロファイル保存・読み込み ---
function saveProfile(profile) {
  localStorage.setItem("profile", JSON.stringify(profile));
}

function loadProfile() {
  const data = localStorage.getItem("profile");
  return data ? JSON.parse(data) : {};
}

// --- チャット送信処理 ---
async function sendMessage(message, data){
  const profile = loadProfile(); // localStorageから読み込み
  addMessage('user', message);

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message, data, profile})
  });

  const j = await res.json();
  addMessage('bot', j.reply || JSON.stringify(j));

  // サーバーから返ってきた profile を更新して保存
  if(j.profile){
    saveProfile(j.profile);
  }
}

// --- スケジュールフォーム送信処理 ---
scheduleForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const title = document.getElementById('sch_title').value || '無題';
  const datetime = document.getElementById('sch_datetime').value;
  const items = (document.getElementById('sch_items').value || '')
                 .split(',')
                 .map(s=>s.trim())
                 .filter(Boolean);

  if(!datetime){
    alert('日時を入力してください');
    return;
  }

  await sendMessage('予定を追加', {title, datetime, items});
  scheduleForm.reset();
});

// --- 食事フォーム送信処理 ---
mealForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const date = document.getElementById('meal_date').value;
  const meal_type = document.getElementById('meal_type').value || '食事';
  const items = document.getElementById('meal_items').value || '';
  const calories = parseInt(document.getElementById('meal_cal').value) || null;
  const rating = parseInt(document.getElementById('meal_rating').value) || null;
  const notes = document.getElementById('meal_notes').value || null;

  if(!date){
    alert('日付を入力してください');
    return;
  }

  await sendMessage('食事記録追加', {date, meal_type, items, calories, rating, notes});
  mealForm.reset();
});

// --- 起動時にプロファイルを読み込んでUIに反映 ---
document.addEventListener("DOMContentLoaded", () => {
  const profile = loadProfile();
  if(profile.nickname){
    document.getElementById("nickname_display").textContent = profile.nickname;
  }
  if(profile.region){
    document.getElementById("region_display").textContent = profile.region;
  }
});