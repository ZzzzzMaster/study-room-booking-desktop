/* 视图：登录（含管理员入口）/ 注册 —— 两个独立路由页面 */
var Views = window.Views = {};

Views.login = function () {
  const adminMode = App.entry === 'admin';
  document.getElementById('view').innerHTML = `
    <div class="auth-wrap">
      <div class="card auth-card">
        <h2>学校自习室预约系统</h2>
        ${adminMode ? '<div class="hint-box">已选择<strong>管理员后台入口</strong>，请使用管理员账号登录（默认学号 1160423527）。</div>' : ''}
        <div class="field"><label>学号</label><input id="f-student-id" autocomplete="username"></div>
        <div class="field"><label>密码</label><input id="f-password" type="password" autocomplete="current-password"></div>
        <div class="err-text" id="login-err"></div>
        <button class="btn" id="btn-login">登 录</button>
        <div class="switch-tip">还没有账号？<a href="#/register">去注册</a></div>
        <a class="link-mini" href="#/login" id="admin-entry">${adminMode ? '← 返回学生登录' : '管理员后台入口 →'}</a>
      </div>
    </div>`;

  document.getElementById('admin-entry').onclick = (e) => {
    e.preventDefault();
    App.entry = adminMode ? '' : 'admin';
    Views.login();
  };

  const doLogin = async () => {
    const studentId = document.getElementById('f-student-id').value.trim();
    const password = document.getElementById('f-password').value;
    const err = document.getElementById('login-err');
    err.textContent = '';
    if (!studentId || !password) { err.textContent = '请输入学号和密码'; return; }
    try {
      const data = await Api.post('/api/login', { student_id: studentId, password });
      Api.setAuth(data.token, data.user);
      Ws.close();
      Ws.connect();
      App.entry = '';
      if (App.next) {
        location.hash = App.next;
        App.next = '';
      } else if (data.user.role === 'admin') {
        location.hash = '#/admin';
      } else {
        location.hash = '#/rooms';
      }
    } catch (e) {
      err.textContent = e.message;
    }
  };
  document.getElementById('btn-login').onclick = doLogin;
  document.getElementById('f-password').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
};

Views.register = function () {
  document.getElementById('view').innerHTML = `
    <div class="auth-wrap">
      <div class="card auth-card">
        <h2>学生注册</h2>
        <div class="field"><label>学号</label><input id="f-student-id" autocomplete="username"></div>
        <div class="field"><label>姓名</label><input id="f-name"></div>
        <div class="field"><label>密码</label><input id="f-password" type="password"></div>
        <div class="field"><label>确认密码</label><input id="f-confirm" type="password"></div>
        <div class="err-text" id="reg-err"></div>
        <button class="btn" id="btn-register">注 册</button>
        <div class="switch-tip">已有账号？<a href="#/login">去登录</a></div>
      </div>
    </div>`;

  const doRegister = async () => {
    const studentId = document.getElementById('f-student-id').value.trim();
    const name = document.getElementById('f-name').value.trim();
    const password = document.getElementById('f-password').value;
    const confirm = document.getElementById('f-confirm').value;
    const err = document.getElementById('reg-err');
    err.textContent = '';
    if (!studentId || !name || !password) { err.textContent = '请填写完整信息'; return; }
    if (password !== confirm) { err.textContent = '两次输入的密码不一致'; return; }
    try {
      await Api.post('/api/register', {
        student_id: studentId, name, password, confirm_password: confirm,
      });
      Ui.toast('注册成功，请登录', 'success');
      location.hash = '#/login';
    } catch (e) {
      err.textContent = e.message;
    }
  };
  document.getElementById('btn-register').onclick = doRegister;
  document.getElementById('f-confirm').addEventListener('keydown', (e) => { if (e.key === 'Enter') doRegister(); });
};