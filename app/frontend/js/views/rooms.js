/* 视图：自习室列表 / 自习室座位（插座筛选 + 预约面板） */
var Views = window.Views;

Views.rooms = async function () {
  const root = document.getElementById('view');
  root.innerHTML = '<div class="spin">加载中…</div>';
  let rooms;
  try {
    rooms = await Api.get('/api/rooms');
  } catch (e) {
    root.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  root.innerHTML = `
    <h1 class="page-title">自习室列表</h1>
    <div class="grid rooms">
      ${rooms.map((r) => `
        <div class="card room-card">
          <div class="rc-head"><h3>${esc(r.name)}</h3>
            <span class="badge ${r.status === 'open' ? 'green' : 'gray'}">${r.status === 'open' ? '开放中' : '已关闭'}</span>
          </div>
          <div class="meta">📍 ${esc(r.location)}<br>🕐 开放时间 ${fmtTimeHm(r.open_time)} - ${fmtTimeHm(r.close_time)}</div>
          <div class="num-row">
            <span class="badge blue">座位 ${r.seat_total} 个</span>
            <span class="badge ${r.seat_available > 0 ? 'green' : 'gray'}">当前空闲 ${r.seat_available}</span>
          </div>
          <a class="btn sm" href="#/rooms/${r.id}">查看座位 →</a>
        </div>`).join('') || '<div class="empty">暂无自习室</div>'}
    </div>`;
};

Views.room = async function (roomId) {
  const root = document.getElementById('view');
  const state = { power: 'all' };
  root.innerHTML = '<div class="spin">加载中…</div>';

  const load = async () => {
    let data;
    try {
      data = await Api.get(`/api/rooms/${roomId}/seats?power=${state.power}`);
    } catch (e) {
      root.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
      return;
    }
    const room = data.room;
    document.getElementById('seat-body').innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <div><a href="#/rooms">← 返回列表</a>
            <h2 style="margin:6px 0 4px">${esc(room.name)}（${esc(room.location)}）</h2>
            <div class="meta">开放时间 ${fmtTimeHm(room.open_time)} - ${fmtTimeHm(room.close_time)} ·
              <span class="badge ${room.status === 'open' ? 'green' : 'gray'}">${room.status === 'open' ? '开放中' : '已关闭'}</span></div>
          </div>
          <div class="tabs" style="margin:0" id="power-tabs">
            ${[['all', '全部'], ['1', '有插座'], ['0', '无插座']].map(([v, t]) =>
              `<button data-power="${v}" class="${state.power === v ? 'active' : ''}">${t}</button>`).join('')}
          </div>
        </div>
      </div>
      <div class="grid seats">
        ${data.seats.map((s) => {
          const st = s.status;
          const clickable = s.bookable;
          return `
          <div class="seat ${st}" data-seat='${JSON.stringify({ id: s.seat_id, no: s.seat_no, has_power: s.has_power })}'>
            <div class="no">${esc(s.seat_no)}</div>
            <div class="ext">${s.has_power ? '⚡ 有插座' : '— 无插座'}</div>
            <div class="st"><span class="badge ${SEAT_BADGE[st]}">${SEAT_LABEL[st]}</span></div>
            <button ${clickable ? '' : 'disabled'}>${clickable ? '预约' : '不可约'}</button>
          </div>`;
        }).join('') || '<div class="empty">该自习室暂无座位</div>'}
      </div>`;

    document.getElementById('power-tabs').querySelectorAll('button').forEach((btn) => {
      btn.onclick = () => { state.power = btn.dataset.power; load(); };
    });
    document.querySelectorAll('.seat.available').forEach((el) => {
      el.querySelector('button').onclick = () => openBookingModal(JSON.parse(el.dataset.seat));
    });
    Views.room.__refresh = load;
  };

  /* 预约面板：日期 + 1 小时粒度起止时间；>4h 前端即拦截 */
  const openBookingModal = (seat) => {
    const today = Ui.dateToday();
    const nowHour = Ui.nowHour();
    const modal = Ui.modal(`预约座位 ${seat.no}`, `
      <div class="field"><label>日期</label><input type="date" id="bk-date" min="${today}" value="${today}"></div>
      <div style="display:flex;gap:12px">
        <div class="field" style="flex:1"><label>开始时间</label><select id="bk-start"></select></div>
        <div class="field" style="flex:1"><label>结束时间</label><select id="bk-end"></select></div>
      </div>
      <div class="hours-line" id="bk-hours"></div>
      <div class="err-text" id="bk-err"></div>
    `, {
      buttons: [
        { text: '取消', cls: 'btn muted' },
        { text: '提交预约', cls: 'btn', click: () => submit() },
      ],
    });

    const dateSel = modal.box.querySelector('#bk-date');
    const startSel = modal.box.querySelector('#bk-start');
    const endSel = modal.box.querySelector('#bk-end');

    const fillStarts = () => {
      const sameDay = dateSel.value === today;
      const opts = Ui.hoursOptions(8, 22).filter((o) => {
        const h = parseInt(o.value, 10);
        if (h < 8 || h > 21) return false;
        return sameDay ? h > nowHour : true;
      });
      startSel.innerHTML = opts.map((o) => `<option value="${o.value}">${o.value}</option>`).join('');
      fillEnds();
    };
    const fillEnds = () => {
      if (!startSel.value) return;
      const sh = parseInt(startSel.value, 10);
      endSel.innerHTML = Ui.hoursOptions(sh + 1, 23)
        .filter((o) => parseInt(o.value, 10) <= 22)
        .map((o) => `<option value="${o.value}">${o.value}</option>`).join('');
      refreshHours();
    };
    const refreshHours = () => {
      const line = modal.box.querySelector('#bk-hours');
      const err = modal.box.querySelector('#bk-err');
      if (!startSel.value || !endSel.value) { line.classList.remove('show'); return; }
      const h = hoursBetween(startSel.value, endSel.value);
      line.classList.add('show');
      if (h > 4) {
        line.textContent = '';
        err.textContent = MAX_MSG;
        line.style.display = 'none';
      } else {
        line.textContent = `共 ${h} 小时（${startSel.value} - ${endSel.value}）`;
        err.textContent = '';
        line.style.display = '';
      }
    };

    const MAX_MSG = '单次预约最长 4 小时，请缩短时间段或分段预约。';
    dateSel.onchange = fillStarts;
    startSel.onchange = fillEnds;
    endSel.onchange = refreshHours;
    fillStarts();

    async function submit() {
      const err = modal.box.querySelector('#bk-err');
      const date = dateSel.value;
      const start = startSel.value, end = endSel.value;
      if (!date) { err.textContent = '请选择日期'; return; }
      if (!start || !end) { err.textContent = '请选择起止时间'; return; }
      if (hoursBetween(start, end) > 4) { err.textContent = MAX_MSG; return; }
      if (date === today && parseInt(start, 10) <= nowHour) {
        err.textContent = '开始时间必须晚于当前时间'; return;
      }
      try {
        await Api.post('/api/bookings', {
          room_id: roomId, seat_id: seat.id, date, start_time: start, end_time: end,
        });
        Ui.toast('预约成功，座位状态已同步', 'success');
        modal.close();
        load();
      } catch (e) {
        err.textContent = e.message;
      }
    }
  };

  root.innerHTML = `
    <div class="spin">加载中…</div>
    <div id="seat-body"></div>`;
  await load();
};