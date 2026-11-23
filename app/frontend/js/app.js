/* 应用入口：hash 路由 + 顶部导航 + WebSocket 事件绑定 */
const App = {
  entry: '',      // 登录页模式：'' 学生 / 'admin' 管理员入口
  next: '',       // 登录后回跳路由
  currentView: null,
  refreshTimer: null,

  routes: [
    { re: /^\/login$/, auth: false, view: () => Views.login() },
    { re: /^\/register$/, auth: false, view: () => Views.register() },
    { re: /^\/rooms$/, auth: true, view: () => Views.rooms() },
    { re: /^\/rooms\/(\d+)$/, auth: true, view: (m) => Views.room(parseInt(m[1], 10)) },
    { re: /^\/my-bookings$/, auth: true, view: () => Views.mybookings() },
    { re: /^\/admin$/, auth: true, adminOnly: true, view: () => Views.admin() },
  ],

  handleRoute() {
    const hash = (location.hash || '#/login').replace(/^#/, '') || '/login';
    const route = this.routes.find((r) => r.re.test(hash));
    if (!route) { location.hash = '#/login'; return; }
    const m = hash.match(/^\/(?:rooms)\/(\d+)$/);

    if (route.auth && !Api.user) {
      this.next = hash;
      location.hash = '#/login';
      return;
    }
    if (route.adminOnly && Api.user && Api.user.role !== 'admin') {
      Ui.toast('该页面仅管理员可访问', 'error');
      location.hash = '#/rooms';
      return;
    }

    this.renderShell({ showTop: route.auth });
    this.currentView = route.view;
    this.currentView(m || null);
  },

  renderShell({ showTop }) {
    const app = document.getElementById('app');
    if (!showTop) {
      app.innerHTML = '<div id="view"></div>';
      return;
    }
    const user = Api.user || {};
    const isAdmin = user.role === 'admin';
    const hash = location.hash || '#/rooms';
    const nav = (item) => `<a href="${item.h}" class="${hash.startsWith(item.h) ? 'active' : ''}">${item.t}</a>`;
    app.innerHTML = `
      <div class="topbar">
        <div class="brand">📚 自习室预约</div>
        <nav>
          ${nav({ h: '#/rooms', t: '自习室' })}
          ${nav({ h: '#/my-bookings', t: '我的预约' })}
          ${isAdmin ? nav({ h: '#/admin', t: '管理后台' }) : ''}
        </nav>
        <div class="user">
          <span>${esc(user.name || '')}<small style="margin-left:6px;color:#94a3b8">${esc(user.student_id || '')}</small></span>
          <button class="btn sm muted" id="btn-logout">退出</button>
        </div>
      </div>
      <div class="container" id="view"></div>`;
    document.getElementById('btn-logout').onclick = () => {
      Ws.close();
      Api.clearAuth();
      location.hash = '#/login';
    };
  },
};

/* WebSocket 事件：实时座位更新 / 到期提醒 / 超时提示 */
Ws.on('seat_updated', (msg) => {
  const p = msg.payload || {};
  if (p.message) Ui.toast(p.message, p.reason === 'expired' ? 'error' : 'success');
  // 正在座位页/列表页时静默刷新（去抖动）
  clearTimeout(App.refreshTimer);
  App.refreshTimer = setTimeout(() => {
    if (Api.user && App.currentView) {
      const hash = location.hash || '';
      if (/^#\/rooms/.test(hash)) App.currentView();
    }
  }, 400);
});

Ws.on('booking_reminder', (msg) => {
  const p = msg.payload || {};
  Ui.modal('⏰ 续约提醒', `<div class="meta">${esc(p.room_name || '')} · ${esc(p.seat_no || '')} · ${esc(p.end_time || '')} 结束</div><p>${esc(msg.message || '')}</p>`, {
    buttons: [
      { text: '知道了', cls: 'btn muted' },
      { text: '去续约', cls: 'btn', click: () => { location.hash = '#/my-bookings'; } },
    ],
  });
});

Ws.on('booking_expired', (msg) => {
  const p = msg.payload || {};
  Ui.modal('⚠️ 预约到期', `<div class="meta">${esc(p.room_name || '')} · ${esc(p.seat_no || '')}</div><p>${esc(msg.message || '')}</p>`, {
    buttons: [
      { text: '立即续约', cls: 'btn', click: () => { location.hash = '#/my-bookings'; } },
      { text: '离开座位', cls: 'btn muted', click: () => { location.hash = '#/my-bookings'; } },
    ],
  });
});

/* 启动 */
window.addEventListener('hashchange', () => App.handleRoute());
window.addEventListener('DOMContentLoaded', () => {
  if (Api.token) Ws.connect();
  App.handleRoute();
});