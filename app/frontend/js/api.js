/* API 封装：REST 请求 + token 会话管理 */
const Api = {
  token: localStorage.getItem('srr_token') || '',
  user: JSON.parse(localStorage.getItem('srr_user') || 'null'),

  setAuth(token, user) {
    this.token = token;
    this.user = user;
    localStorage.setItem('srr_token', token);
    localStorage.setItem('srr_user', JSON.stringify(user));
  },
  clearAuth() {
    this.token = '';
    this.user = null;
    localStorage.removeItem('srr_token');
    localStorage.removeItem('srr_user');
  },

  async request(method, path, body) {
    const headers = {};
    if (this.token) headers['Authorization'] = 'Bearer ' + this.token;
    let payload;
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, { method, headers, body: payload });
    } catch (e) {
      throw new Error('网络请求失败，请确认后端服务已启动');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (res.status === 401 && this.token) {
      this.clearAuth();
      if (location.hash !== '#/login') {
        location.hash = '#/login';
        Ui.toast('登录已过期，请重新登录', 'error');
      }
      throw new Error('未登录或凭证失效');
    }
    if (!res.ok) throw new Error((data && data.error) || ('请求失败（' + res.status + '）'));
    return data ? data.data : null;
  },

  get: (p) => Api.request('GET', p),
  post: (p, b) => Api.request('POST', p, b),
  put: (p, b) => Api.request('PUT', p, b),
  del: (p) => Api.request('DELETE', p),
};

/* 通用渲染小工具 */
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const SEAT_LABEL = {
  available: '空闲', reserved: '已预约', occupied: '使用中', disabled: '已禁用', broken: '已损坏',
};
const SEAT_BADGE = {
  available: 'green', reserved: 'blue', occupied: 'orange', disabled: 'gray', broken: 'red',
};
const BK_LABEL = {
  reserved: '待入座', occupied: '使用中', expired: '已超时释放', completed: '已完成', cancelled: '已取消',
};

function fmtTimeHm(s) { // "HH:MM"
  return s || '';
}
function hoursBetween(start, end) {
  const [h1] = start.split(':').map(Number);
  const [h2] = end.split(':').map(Number);
  return h2 - h1;
}