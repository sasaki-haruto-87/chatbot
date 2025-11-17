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
// 朝のスケジュール生成
const morningScheduleForm = document.getElementById('morningScheduleForm');
const taskList = document.getElementById('taskList');
const addTaskBtn = document.getElementById('addTask');
const scheduleOutput = document.getElementById('scheduleOutput');

function createTaskElement() {
    const taskDiv = document.createElement('div');
    taskDiv.className = 'task-item';
    
    taskDiv.innerHTML = `
        <input type="text" class="task-title" placeholder="タスク名" required />
        <input type="number" class="task-duration" placeholder="所要時間(分)" min="1" required />
        <input type="number" class="task-priority" placeholder="優先度(1-5)" min="1" max="5" value="3" required />
        <button type="button" class="remove-task">削除</button>
    `;
    
    taskDiv.querySelector('.remove-task').addEventListener('click', () => {
        taskDiv.remove();
    });
    
    return taskDiv;
}

addTaskBtn.addEventListener('click', () => {
    taskList.appendChild(createTaskElement());
});

morningScheduleForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const wakeUpTime = document.getElementById('wakeUpTime').value;
    const departureTime = document.getElementById('departureTime').value;
    
    if (!wakeUpTime || !departureTime) {
        alert('起床時刻と出発時刻は必須です');
        return;
    }
    
    const tasks = Array.from(taskList.querySelectorAll('.task-item')).map(task => ({
        title: task.querySelector('.task-title').value,
        duration: parseInt(task.querySelector('.task-duration').value),
        priority: parseInt(task.querySelector('.task-priority').value)
    }));
    
    try {
        const response = await fetch('/api/generate_schedule', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({wakeUpTime, departureTime, tasks})
        });
        
        const data = await response.json();
        if (data.error) {
            alert('エラー: ' + data.error);
            return;
        }
        
        // スケジュールの表示
        document.getElementById('scheduleResult').style.display = 'block';
        scheduleOutput.innerHTML = '';
        
        data.schedule.forEach(item => {
            const div = document.createElement('div');
            div.className = 'schedule-item';
            div.innerHTML = `
                <div class="time">${item.start} - ${item.end}</div>
                <div class="title">${item.title}</div>
                <div class="reason">${item.reason}</div>
            `;
            scheduleOutput.appendChild(div);
        });
        
        if (data.warnings && data.warnings.length > 0) {
            const warningsDiv = document.createElement('div');
            warningsDiv.style.color = '#ef4444';
            warningsDiv.style.marginTop = '10px';
            warningsDiv.innerHTML = '<strong>注意:</strong><br>' + data.warnings.join('<br>');
            scheduleOutput.appendChild(warningsDiv);
        }
        
    } catch (error) {
        alert('エラーが発生しました: ' + error);
    }
});

// デフォルトのタスクを追加
taskList.appendChild(createTaskElement());

const mealForm = document.getElementById('mealForm');
mealForm.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const meal_type = document.getElementById('meal_type').value || '食事';
  const items = document.getElementById('meal_items').value || '';
  const calories = parseInt(document.getElementById('meal_cal').value) || null;
  await sendMessage('食事記録', {meal_type, items, calories});
  mealForm.reset();
});
