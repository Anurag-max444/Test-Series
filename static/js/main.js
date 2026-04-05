// ── Toast System ──────────────────────────────────────────────────────────────
const Toast = {
  container: null,
  init() {
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  },
  show(msg, type = 'info', duration = 4000) {
    this.init();
    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerHTML = `<span class="toast-icon">${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
    this.container.appendChild(t);
    setTimeout(() => {
      t.style.animation = 'slideIn .3s ease reverse';
      setTimeout(() => t.remove(), 280);
    }, duration);
  }
};

// ── Page Spinner ──────────────────────────────────────────────────────────────
const Spinner = {
  show() {
    const s = document.createElement('div');
    s.id = 'page-spinner'; s.className = 'page-spinner';
    s.innerHTML = '<div class="spinner-ring"></div>';
    document.body.appendChild(s);
  },
  hide() {
    const s = document.getElementById('page-spinner');
    if (s) s.remove();
  }
};

// ── Flash Messages → Toasts ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-msg').forEach(el => {
    Toast.show(el.dataset.msg, el.dataset.type || 'info');
  });

  // Mobile nav
  const hamburger = document.querySelector('.hamburger');
  const mobileMenu = document.querySelector('.mobile-menu');
  if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
    });
  }

  // Active nav link
  const path = window.location.pathname;
  document.querySelectorAll('.nav-links a, .mobile-menu a').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });
});

// ── Modal System ──────────────────────────────────────────────────────────────
function showComingSoon(name, icon = '🚀') {
  const overlay = document.getElementById('coming-soon-modal');
  if (overlay) {
    overlay.querySelector('.modal-anim').textContent = icon;
    overlay.querySelector('.modal-title').textContent = name;
    overlay.classList.add('open');
  }
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// ── Quiz Engine ───────────────────────────────────────────────────────────────
let quizState = null;

function initQuiz(questions) {
  quizState = {
    questions, current: 0,
    answers: {}, startTime: Date.now(),
    questionStart: Date.now(),
    timerInterval: null
  };
  renderQuestion();
  startTimer();
}

function renderQuestion() {
  if (!quizState) return;
  const q = quizState.questions[quizState.current];
  const total = quizState.questions.length;
  const num = quizState.current + 1;

  document.getElementById('q-num').textContent = `Question ${num} of ${total}`;
  document.getElementById('q-text').textContent = q.question;

  const pct = ((num - 1) / total * 100);
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent = `${num - 1}/${total}`;

  const optionsEl = document.getElementById('options');
  optionsEl.innerHTML = '';
  Object.entries(q.options).forEach(([key, val]) => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.dataset.key = key;
    btn.innerHTML = `<span class="option-label">${key}</span><span>${val}</span>`;
    btn.onclick = () => selectAnswer(key);
    optionsEl.appendChild(btn);
  });

  const explanBox = document.getElementById('explanation');
  if (explanBox) explanBox.style.display = 'none';

  const nextBtn = document.getElementById('next-btn');
  if (nextBtn) {
    nextBtn.textContent = quizState.current === total - 1 ? '🏁 Submit Quiz' : 'Next →';
    nextBtn.disabled = true;
  }
  quizState.questionStart = Date.now();
}

function selectAnswer(key) {
  if (!quizState) return;
  const q = quizState.questions[quizState.current];
  quizState.answers[q.id] = key;

  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.disabled = true;
    if (btn.dataset.key === q.correct) btn.classList.add('correct');
    else if (btn.dataset.key === key && key !== q.correct) btn.classList.add('wrong');
    if (btn.dataset.key === key) btn.classList.add('selected');
  });

  const explanBox = document.getElementById('explanation');
  if (explanBox && q.explanation) {
    explanBox.textContent = '💡 ' + q.explanation;
    explanBox.style.display = 'block';
  }

  const nextBtn = document.getElementById('next-btn');
  if (nextBtn) nextBtn.disabled = false;
}

function nextQuestion() {
  if (!quizState) return;
  quizState.current++;
  if (quizState.current >= quizState.questions.length) {
    submitQuiz();
  } else {
    renderQuestion();
    resetTimer();
  }
}

function startTimer() {
  const timerEl = document.getElementById('timer');
  if (!timerEl) return;
  let seconds = 60;
  timerEl.textContent = seconds;
  clearInterval(quizState.timerInterval);
  quizState.timerInterval = setInterval(() => {
    seconds--;
    timerEl.textContent = seconds;
    if (seconds <= 10) timerEl.style.color = '#f59e0b';
    if (seconds <= 0) {
      clearInterval(quizState.timerInterval);
      autoNext();
    }
  }, 1000);
}

function resetTimer() {
  const timerEl = document.getElementById('timer');
  if (timerEl) timerEl.style.color = '';
  startTimer();
}

function autoNext() {
  Toast.show('Time up! Moving to next question.', 'warning', 2000);
  quizState.current++;
  if (quizState.current >= quizState.questions.length) {
    submitQuiz();
  } else {
    renderQuestion();
  }
}

async function submitQuiz() {
  clearInterval(quizState.timerInterval);
  Spinner.show();
  const timeTaken = Math.round((Date.now() - quizState.startTime) / 1000);
  try {
    const res = await fetch('/quiz/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ answers: quizState.answers, time_taken: timeTaken })
    });
    const data = await res.json();
    Spinner.hide();
    showResult(data.score, data.total);
  } catch (e) {
    Spinner.hide();
    Toast.show('Error submitting quiz. Please try again.', 'error');
  }
}

function showResult(score, total) {
  const pct = Math.round(score / total * 100);
  const container = document.getElementById('quiz-container');
  if (!container) return;
  const grade = pct >= 90 ? '🏆 Excellent!' : pct >= 70 ? '🎉 Great Job!' : pct >= 50 ? '👍 Good Effort' : '📚 Keep Practicing';
  container.innerHTML = `
    <div class="result-card fade-in">
      <div class="score-circle" style="--pct:${pct * 3.6}deg">
        <span>${pct}%</span>
      </div>
      <h2>${grade}</h2>
      <p>You scored <strong style="color:var(--accent)">${score}</strong> out of <strong>${total}</strong> questions correctly.</p>
      <div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap">
        <a href="/quiz" class="btn btn-secondary">← Back to Tests</a>
        <a href="/dashboard" class="btn btn-primary">🏠 Dashboard</a>
        <a href="/leaderboard" class="btn btn-secondary">🏆 Leaderboard</a>
      </div>
    </div>
  `;
}

// ── Chat System ───────────────────────────────────────────────────────────────
let chatInterval = null;
let currentUser = null;

async function initChat(username) {
  currentUser = username;
  await loadMessages();
  chatInterval = setInterval(loadMessages, 3000);
  const input = document.getElementById('chat-input');
  if (input) {
    input.addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
  }
}

async function loadMessages() {
  try {
    const res = await fetch('/chat/messages');
    const data = await res.json();
    renderMessages(data.messages);
  } catch(e) {}
}

function renderMessages(messages) {
  const box = document.getElementById('chat-box');
  if (!box) return;
  const wasAtBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 20;
  box.innerHTML = messages.map(m => {
    const isMe = m.user_name === currentUser;
    const initials = m.user_name.charAt(0).toUpperCase();
    const time = new Date(m.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
    return `<div class="chat-msg ${isMe ? 'me' : ''}">
      <div class="chat-avatar">${initials}</div>
      <div class="chat-bubble">
        ${!isMe ? `<div class="chat-name">${m.user_name}</div>` : ''}
        <div class="chat-text">${escapeHtml(m.message)}</div>
        <div class="chat-time">${time}</div>
      </div>
    </div>`;
  }).join('');
  if (wasAtBottom) box.scrollTop = box.scrollHeight;
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  try {
    const res = await fetch('/chat/send', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await res.json();
    renderMessages(data.messages);
    document.getElementById('chat-box').scrollTop = 99999;
  } catch(e) { Toast.show('Failed to send message', 'error'); }
}

// ── Comments ──────────────────────────────────────────────────────────────────
async function loadComments(cls, sub, chap) {
  try {
    const res = await fetch(`/comments/get?class_name=${cls}&subject=${sub}&chapter=${encodeURIComponent(chap)}`);
    const data = await res.json();
    const box = document.getElementById('comments-list');
    if (!box) return;
    if (!data.length) { box.innerHTML = '<p class="text-muted text-sm">No comments yet. Be the first!</p>'; return; }
    box.innerHTML = data.map(c => `
      <div class="chat-msg" style="margin-bottom:.75rem">
        <div class="chat-avatar">${c.user_name.charAt(0).toUpperCase()}</div>
        <div class="chat-bubble">
          <div class="chat-name">${c.user_name}</div>
          <div class="chat-text">${escapeHtml(c.comment)}</div>
          <div class="chat-time">${new Date(c.created_at).toLocaleDateString()}</div>
        </div>
      </div>`).join('');
  } catch(e) {}
}

async function submitComment(cls, sub, chap) {
  const input = document.getElementById('comment-input');
  const comment = input.value.trim();
  if (!comment) return;
  try {
    await fetch('/comments/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({class_name: cls, subject: sub, chapter: chap, comment})
    });
    input.value = '';
    loadComments(cls, sub, chap);
    Toast.show('Comment added!', 'success');
  } catch(e) { Toast.show('Failed to post comment', 'error'); }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
