/* WebSocket 管理：连接、心跳、消息分发、断线重连 */
const Ws = {
  sock: null,
  handlers: {},
  reconnectTimer: null,
  pingTimer: null,

  on(type, fn) {
    (this.handlers[type] = this.handlers[type] || []).push(fn);
  },
  emit(type, msg) {
    (this.handlers[type] || []).forEach((fn) => fn(msg));
  },

  connect() {
    clearTimeout(this.reconnectTimer);
    if (!Api.token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    try { this.sock = new WebSocket(proto + '://' + location.host + '/ws?token=' + encodeURIComponent(Api.token)); }
    catch (e) { return; }
    this.sock.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (err) { return; }
      if (msg && msg.type) this.emit(msg.type, msg);
    };
    this.sock.onclose = () => {
      this.sock = null;
      clearInterval(this.pingTimer);
      if (Api.token) this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };
    this.sock.onerror = () => { try { this.sock.close(); } catch (e) { /* ignore */ } };
    clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => {
      if (this.sock && this.sock.readyState === 1) {
        try { this.sock.send(JSON.stringify({ type: 'ping' })); } catch (e) { /* ignore */ }
      }
    }, 30000);
  },

  close() {
    clearTimeout(this.reconnectTimer);
    clearInterval(this.pingTimer);
    this.reconnectTimer = null;
    this.pingTimer = null;
    if (this.sock) { try { this.sock.close(); } catch (e) { /* ignore */ } }
    this.sock = null;
  },
};