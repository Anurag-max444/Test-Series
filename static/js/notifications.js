// ── QuizMaster Pro — Notification System ─────────────────────────────────────
// Handles: bell badge, dropdown, mark-as-read, auto-poll

const NotifSystem = {
  pollInterval: null,
  isOpen: false,

  // ── Init ────────────────────────────────────────────────────────────────────
  init(isLoggedIn) {
    if (!isLoggedIn) return;
    this.render();
    this.fetch();
    // Auto-refresh every 30 seconds
    this.pollInterval = setInterval(() => this.fetch(), 30000);

    // Close dropdown on outside click
    document.addEventListener('click', e => {
      const wrapper = document.getElementById('notif-wrapper');
      if (wrapper && !wrapper.contains(e.target)) this.close();
    });

    // Track last-online time for offline page
    localStorage.setItem('qm_last_online', Date.now());
  },

  // ── Inject bell into navbar ─────────────────────────────────────────────────
  render() {
    const navUser = document.querySelector('.nav-user');
    if (!navUser || document.getElementById('notif-wrapper')) return;

    const wrapper = document.createElement('div');
    wrapper.id        = 'notif-wrapper';
    wrapper.className = 'notif-wrapper';
    wrapper.innerHTML = `
      <button class="notif-bell" id="notif-bell" onclick="NotifSystem.toggle()" aria-label="Notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        <span class="notif-badge" id="notif-badge" style="display:none">0</span>
      </button>
      <div class="notif-dropdown" id="notif-dropdown">
        <div class="notif-header">
          <span>🔔 Notifications</span>
          <button class="notif-mark-all" onclick="NotifSystem.markAllRead()">Mark all read</button>
        </div>
        <div class="notif-list" id="notif-list">
          <div class="notif-empty">No notifications yet</div>
        </div>
      </div>
    `;
    // Insert before the first child of nav-user
    navUser.insertBefore(wrapper, navUser.firstChild);
  },

  // ── Fetch notifications from server ────────────────────────────────────────
  async fetch() {
    try {
      const res  = await fetch('/notifications/get');
      if (!res.ok) return;
      const data = await res.json();
      this.update(data.notifications || [], data.unread_count || 0);
    } catch(e) { /* Offline or server error — silent */ }
  },

  // ── Update UI ───────────────────────────────────────────────────────────────
  update(notifications, unreadCount) {
    const badge  = document.getElementById('notif-badge');
    const list   = document.getElementById('notif-list');
    if (!badge || !list) return;

    // Badge
    if (unreadCount > 0) {
      badge.style.display = 'flex';
      badge.textContent   = unreadCount > 99 ? '99+' : unreadCount;
    } else {
      badge.style.display = 'none';
    }

    // List
    if (!notifications.length) {
      list.innerHTML = '<div class="notif-empty">🎉 You\'re all caught up!</div>';
      return;
    }

    list.innerHTML = notifications.map(n => `
      <div class="notif-item ${n.is_read ? 'read' : 'unread'}" data-id="${n.id}">
        <div class="notif-dot"></div>
        <div class="notif-body">
          <div class="notif-title">${escapeHtml(n.title)}</div>
          <div class="notif-msg">${escapeHtml(n.message)}</div>
          <div class="notif-time">${this.timeAgo(n.created_at)}</div>
        </div>
        ${!n.is_read ? `<button class="notif-read-btn" onclick="NotifSystem.markRead(${n.id}, this)" title="Mark as read">✓</button>` : ''}
      </div>
    `).join('');
  },

  // ── Toggle dropdown ─────────────────────────────────────────────────────────
  toggle() {
    this.isOpen ? this.close() : this.open();
  },
  open() {
    document.getElementById('notif-dropdown')?.classList.add('open');
    this.isOpen = true;
    this.fetch(); // Refresh on open
  },
  close() {
    document.getElementById('notif-dropdown')?.classList.remove('open');
    this.isOpen = false;
  },

  // ── Mark single notification as read ───────────────────────────────────────
  async markRead(id, btn) {
    try {
      await fetch(`/notifications/read/${id}`, { method: 'POST' });
      const item = document.querySelector(`.notif-item[data-id="${id}"]`);
      if (item) {
        item.classList.remove('unread');
        item.classList.add('read');
        if (btn) btn.remove();
        const dot = item.querySelector('.notif-dot');
        if (dot) dot.style.background = 'transparent';
      }
      this.fetch();
    } catch(e) {}
  },

  // ── Mark all as read ────────────────────────────────────────────────────────
  async markAllRead() {
    try {
      await fetch('/notifications/read-all', { method: 'POST' });
      this.fetch();
      Toast.show('All notifications marked as read', 'success');
    } catch(e) {}
  },

  // ── Helpers ─────────────────────────────────────────────────────────────────
  timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = Date.now() - new Date(isoStr).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)   return 'Just now';
    if (m < 60)  return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24)  return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }
};

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── PWA: Install prompt ───────────────────────────────────────────────────────
const PWA = {
  deferredPrompt: null,

  init() {
    window.addEventListener('beforeinstallprompt', e => {
      e.preventDefault();
      this.deferredPrompt = e;
      this.showBanner();
    });

    window.addEventListener('appinstalled', () => {
      this.hideBanner();
      Toast.show('QuizMaster Pro installed! 🎉', 'success', 4000);
      this.deferredPrompt = null;
    });

    // Register service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/static/sw.js', { scope: '/' })
        .then(reg => console.log('[SW] Registered, scope:', reg.scope))
        .catch(err => console.warn('[SW] Registration failed:', err));
    }

    // Online/offline events
    window.addEventListener('offline', () => {
      Toast.show('You are offline. Some features may be unavailable.', 'warning', 5000);
    });
    window.addEventListener('online', () => {
      Toast.show('Back online!', 'success', 3000);
      localStorage.setItem('qm_last_online', Date.now());
    });
  },

  showBanner() {
    // Only show if not already installed or dismissed recently
    if (localStorage.getItem('qm_pwa_dismissed')) return;
    if (!document.getElementById('pwa-banner')) {
      const banner = document.createElement('div');
      banner.id        = 'pwa-banner';
      banner.className = 'pwa-banner fade-in';
      banner.innerHTML = `
        <div class="pwa-banner-content">
          <div class="pwa-banner-icon">
            <img src="/static/icons/icon-72x72.svg" width="36" height="36" alt="QuizMaster">
          </div>
          <div class="pwa-banner-text">
            <strong>Install QuizMaster Pro</strong>
            <span>Add to home screen for quick access</span>
          </div>
          <button class="btn btn-primary btn-sm" onclick="PWA.install()">Install</button>
          <button class="pwa-dismiss" onclick="PWA.hideBanner(true)" aria-label="Dismiss">✕</button>
        </div>
      `;
      document.body.appendChild(banner);
    }
  },

  async install() {
    if (!this.deferredPrompt) return;
    this.deferredPrompt.prompt();
    const { outcome } = await this.deferredPrompt.userChoice;
    if (outcome === 'accepted') this.hideBanner();
    this.deferredPrompt = null;
  },

  hideBanner(remember = false) {
    const b = document.getElementById('pwa-banner');
    if (b) b.remove();
    if (remember) {
      // Don't show again for 7 days
      localStorage.setItem('qm_pwa_dismissed', Date.now() + 7 * 86400000);
    }
  }
};

// ── Loading Screen ────────────────────────────────────────────────────────────
const LoadingScreen = {
  el: null,

  show(msg = 'Loading...') {
    if (this.el) return;
    this.el = document.createElement('div');
    this.el.id        = 'loading-screen';
    this.el.className = 'loading-screen';
    this.el.innerHTML = `
      <div class="loading-card">
        <div class="loading-logo">
          <img src="/static/icons/icon-96x96.svg" width="64" height="64" alt="QuizMaster">
        </div>
        <div class="loading-ring">
          <svg viewBox="0 0 50 50" class="loading-spinner-svg">
            <circle cx="25" cy="25" r="20" fill="none" stroke="var(--accent)" stroke-width="3"
                    stroke-dasharray="80 40" stroke-linecap="round">
              <animateTransform attributeName="transform" type="rotate"
                                from="0 25 25" to="360 25 25" dur="1s" repeatCount="indefinite"/>
            </circle>
          </svg>
        </div>
        <p class="loading-msg">${msg}</p>
      </div>
    `;
    document.body.appendChild(this.el);
  },

  hide() {
    if (this.el) { this.el.remove(); this.el = null; }
  }
};

// ── Initialise everything on DOMContentLoaded ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  PWA.init();

  // Check if user is logged in (meta tag set by base.html)
  const isLoggedIn = document.querySelector('meta[name="user-logged-in"]')?.content === 'true';
  NotifSystem.init(isLoggedIn);

  // Check for expired PWA dismiss
  const dismissed = localStorage.getItem('qm_pwa_dismissed');
  if (dismissed && Date.now() > parseInt(dismissed)) {
    localStorage.removeItem('qm_pwa_dismissed');
  }
});
