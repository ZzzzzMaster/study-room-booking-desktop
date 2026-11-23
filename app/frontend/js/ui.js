/* UI 帮助：toast、模态框、通用表单 */
const Ui = {
  toast(msg, type) {
    const wrap = document.getElementById('toast-wrap');
    const div = document.createElement('div');
    div.className = 'toast ' + (type || '');
    div.textContent = msg;
    wrap.appendChild(div);
    setTimeout(() => { div.remove(); }, 3500);
  },

  modal(title, bodyHtml, options = {}) {
    const mask = document.getElementById('modal-mask');
    const box = document.getElementById('modal-box');
    const buttons = (options.buttons || [{ text: '关闭', cls: 'btn muted' }]);
    const buttonsHtml = buttons.map((b) => `<button class="${b.cls || 'btn muted'}">${esc(b.text)}</button>`).join('');
    box.innerHTML = `<h3>${esc(title)}</h3>${bodyHtml}<div class="ops">${buttonsHtml}</div>`;
    mask.classList.remove('hidden');
    const close = () => { mask.classList.add('hidden'); box.innerHTML = ''; };
    buttons.forEach((b, i) => {
      const btn = box.querySelectorAll('.ops button')[i];
      if (!btn) return;
      btn.onclick = () => {
        const r = b.click && b.click();
        if (r !== false) close();
      };
    });
    return { close, box };
  },

  confirm(title, bodyHtml, onOk) {
    return this.modal(title, bodyHtml, {
      buttons: [
        { text: '取消', cls: 'btn muted' },
        { text: '确定', cls: 'btn danger', click: onOk },
      ],
    });
  },

  hoursOptions(startHour, endHourExclusive) {
    const opts = [];
    for (let h = startHour; h < endHourExclusive; h++) {
      const t = String(h).padStart(2, '0') + ':00';
      opts.push({ value: t, label: t });
    }
    return opts;
  },

  dateToday() {
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  },

  nowHour() {
    return new Date().getHours();
  },
};