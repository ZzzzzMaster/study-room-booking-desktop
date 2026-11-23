/* 视图：管理后台 —— 自习室管理 / 座位管理（含 禁用/损坏 状态）/ 预约监控 */
var Views = window.Views;

Views.admin = async function () {
  const root = document.getElementById('view');
  const state = { tab: 'rooms' };
  root.innerHTML = `
    <h1 class="page-title">管理后台</h1>
    <div class="tabs" id="admin-tabs">
      <button data-tab="rooms" class="active">自习室管理</button>
      <button data-tab="seats">座位管理</button>
      <button data-tab="bookings">预约监控</button>
    </div>
    <div id="admin-body"></div>`;

  document.getElementById('admin-tabs').querySelectorAll('button').forEach((btn) => {
    btn.onclick = () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll('#admin-tabs button').forEach((b) => b.classList.toggle('active', b === btn));
      render();
    };
  });

  const render = async () => {
    const body = document.getElementById('admin-body');
    body.innerHTML = '<div class="spin">加载中…</div>';
    if (state.tab === 'rooms') await renderRooms(body);
    else if (state.tab === 'seats') await renderSeats(body);
    else await renderBookings(body);
  };

  /* ── 自习室管理 ── */
  const renderRooms = async (body) => {
    let rooms;
    try { rooms = await Api.get('/api/rooms'); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    body.innerHTML = `
      <div class="admin-form">
        <div class="field"><label>名称</label><input id="nr-name" placeholder="如：图书馆四楼自习室"></div>
        <div class="field"><label>位置</label><input id="nr-loc" placeholder="如：图书馆 4F"></div>
        <div class="field"><label>开放</label><select id="nr-open">${hourOpts(8, 21)}</select></div>
        <div class="field"><label>关闭</label><select id="nr-close">${hourOpts(9, 22)}</select></div>
        <button class="btn sm" id="nr-add">新增自习室</button>
      </div>
      <table class="tbl">
        <tr><th>ID</th><th>名称 / 位置</th><th>开放时间</th><th>座位</th><th>空闲</th><th>状态</th><th>操作</th></tr>
        ${rooms.map((r) => `
          <tr data-id="${r.id}">
            <td>${r.id}</td><td><strong>${esc(r.name)}</strong><br><span class="meta">${esc(r.location)}</span></td>
            <td>${esc(r.open_time)} - ${esc(r.close_time)}</td>
            <td>${r.seat_total}</td><td>${r.seat_available}</td>
            <td><span class="badge ${r.status === 'open' ? 'green' : 'gray'}">${r.status === 'open' ? '开放' : '关闭'}</span></td>
            <td>
              <button class="btn sm" data-act="edit">编辑</button>
              <button class="btn sm muted" data-act="toggle">${r.status === 'open' ? '关闭' : '开放'}</button>
              <button class="btn sm danger" data-act="del">删除</button>
            </td>
          </tr>`).join('')}
      </table>`;

    body.querySelector('#nr-add').onclick = async () => {
      const name = body.querySelector('#nr-name').value.trim();
      const location = body.querySelector('#nr-loc').value.trim();
      const openT = body.querySelector('#nr-open').value;
      const closeT = body.querySelector('#nr-close').value;
      if (!name) { Ui.toast('请输入自习室名称', 'error'); return; }
      try {
        await Api.post('/api/admin/rooms', { name, location, open_time: openT, close_time: closeT, status: 'open' });
        Ui.toast('自习室已创建', 'success');
        render();
      } catch (e) { Ui.toast(e.message, 'error'); }
    };
    body.querySelectorAll('[data-act]').forEach((btn) => {
      const rid = Number(btn.closest('tr').dataset.id);
      const room = rooms.find((r) => r.id === rid);
      btn.onclick = async () => {
        const act = btn.dataset.act;
        if (act === 'toggle') {
          try {
            await Api.put(`/api/admin/rooms/${rid}`, { status: room.status === 'open' ? 'closed' : 'open' });
            Ui.toast('状态已更新', 'success');
            render();
          } catch (e) { Ui.toast(e.message, 'error'); }
        } else if (act === 'edit') {
          editRoomModal(room, render);
        } else if (act === 'del') {
          Ui.confirm('删除自习室', `确定删除 <strong>${esc(room.name)}</strong>？（存在预约记录时系统会拒绝）`, async () => {
            try {
              await Api.del(`/api/admin/rooms/${rid}`);
              Ui.toast('已删除', 'success');
              render();
            } catch (e) { Ui.toast(e.message, 'error'); }
          });
        }
      };
    });
  };

  function editRoomModal(room, refresh) {
    const modal = Ui.modal(`编辑自习室 #${room.id}`, `
      <div class="field"><label>名称</label><input id="er-name" value="${esc(room.name)}"></div>
      <div class="field"><label>位置</label><input id="er-loc" value="${esc(room.location)}"></div>
      <div style="display:flex;gap:12px">
        <div class="field" style="flex:1"><label>开放时间</label><select id="er-open">${hourOpts(8, 21, room.open_time)}</select></div>
        <div class="field" style="flex:1"><label>关闭时间</label><select id="er-close">${hourOpts(9, 22, room.close_time)}</select></div>
      </div>
      <div class="field"><label>状态</label>
        <select id="er-status"><option value="open" ${room.status === 'open' ? 'selected' : ''}>开放</option>
        <option value="closed" ${room.status === 'closed' ? 'selected' : ''}>关闭</option></select></div>
    `, {
      buttons: [
        { text: '取消', cls: 'btn muted' },
        { text: '保存', cls: 'btn', click: async () => {
            try {
              await Api.put(`/api/admin/rooms/${room.id}`, {
                name: modal.box.querySelector('#er-name').value.trim(),
                location: modal.box.querySelector('#er-loc').value.trim(),
                open_time: modal.box.querySelector('#er-open').value,
                close_time: modal.box.querySelector('#er-close').value,
                status: modal.box.querySelector('#er-status').value,
              });
              Ui.toast('保存成功', 'success');
              refresh();
            } catch (e) { Ui.toast(e.message, 'error'); return false; }
          } },
      ],
    });
  }

  /* ── 座位管理 ── */
  const renderSeats = async (body) => {
    let rooms;
    try {
      rooms = await Api.get('/api/rooms');
    } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (!rooms.length) { body.innerHTML = '<div class="empty">请先创建自习室</div>'; return; }
    body.innerHTML = `
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:14px">
        <label style="font-size:13px;color:var(--muted)">选择自习室</label>
        <select id="seat-room" style="padding:8px;border-radius:8px;border:1px solid var(--border)">
          ${rooms.map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join('')}
        </select>
      </div>
      <div class="admin-form">
        <div class="field"><label>座位号</label><input id="ns-no" placeholder="如：13号"></div>
        <div class="field"><label>有插座</label><select id="ns-power"><option value="0">无</option><option value="1">有</option></select></div>
        <button class="btn sm" id="ns-add">新增座位</button>
      </div>
      <div id="seat-list"><div class="spin">加载中…</div></div>`;

    const roomSel = body.querySelector('#seat-room');
    let roomId = Number(roomSel.value);
    const loadSeats = async () => {
      roomId = Number(roomSel.value);
      const list = body.querySelector('#seat-list');
      let data;
      try { data = await Api.get(`/api/rooms/${roomId}/seats?power=all`); }
      catch (e) { list.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
      list.innerHTML = `
        <table class="tbl">
          <tr><th>ID</th><th>座位号</th><th>插座</th><th>状态</th><th>操作</th></tr>
          ${data.seats.map((s) => `
            <tr data-id="${s.seat_id}">
              <td>${s.seat_id}</td><td><strong>${esc(s.seat_no)}</strong></td>
              <td>${s.has_power ? '⚡ 有' : '— 无'}</td>
              <td><span class="badge ${SEAT_BADGE[s.status]}">${SEAT_LABEL[s.status]}</span></td>
              <td>
                <select class="st-sel" style="padding:6px;border-radius:8px;border:1px solid var(--border)">
                  <option value="available" ${s.status === 'available' ? 'selected' : ''}>空闲</option>
                  <option value="disabled" ${s.status === 'disabled' ? 'selected' : ''}>禁用</option>
                  <option value="broken" ${s.status === 'broken' ? 'selected' : ''}>损坏</option>
                </select>
                <button class="btn sm danger" data-act="del">删除</button>
              </td>
            </tr>`).join('')}
        </table>`;
      list.querySelectorAll('.st-sel').forEach((sel) => {
        sel.onchange = async () => {
          const sid = Number(sel.closest('tr').dataset.id);
          try {
            await Api.put(`/api/admin/seats/${sid}/status`, { status: sel.value });
            Ui.toast('座位状态已更新', 'success');
            loadSeats();
          } catch (e) { Ui.toast(e.message, 'error'); loadSeats(); }
        };
      });
      list.querySelectorAll('[data-act="del"]').forEach((btn) => {
        btn.onclick = () => {
          const sid = Number(btn.closest('tr').dataset.id);
          const seat = data.seats.find((s) => s.seat_id === sid);
          Ui.confirm('删除座位', `确定删除座位 <strong>${esc(seat.seat_no)}</strong>？（有预约记录时系统会拒绝）`, async () => {
            try {
              await Api.del(`/api/admin/seats/${sid}`);
              Ui.toast('已删除', 'success');
              loadSeats();
            } catch (e) { Ui.toast(e.message, 'error'); }
          });
        };
      });
    };
    roomSel.onchange = loadSeats;
    body.querySelector('#ns-add').onclick = async () => {
      const seatNo = body.querySelector('#ns-no').value.trim();
      const hasPower = body.querySelector('#ns-power').value === '1';
      if (!seatNo) { Ui.toast('请输入座位号', 'error'); return; }
      try {
        await Api.post('/api/admin/seats', { room_id: roomId, seat_no: seatNo, has_power: hasPower });
        Ui.toast('座位已添加', 'success');
        body.querySelector('#ns-no').value = '';
        loadSeats();
      } catch (e) { Ui.toast(e.message, 'error'); }
    };
    await loadSeats();
  };

  /* ── 预约监控 ── */
  const renderBookings = async (body) => {
    const today = Ui.dateToday();
    body.innerHTML = `
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap">
        <label style="font-size:13px;color:var(--muted)">日期</label>
        <input type="date" id="bkf-date" value="${today}" style="padding:7px;border-radius:8px;border:1px solid var(--border)">
        <label style="font-size:13px;color:var(--muted)">状态</label>
        <select id="bkf-status" style="padding:7px;border-radius:8px;border:1px solid var(--border)">
          <option value="">全部</option>
          ${Object.entries(BK_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}
        </select>
        <button class="btn sm" id="bkf-query">查询</button>
      </div>
      <div id="bk-result"><div class="spin">加载中…</div></div>`;

    const load = async () => {
      const date = body.querySelector('#bkf-date').value;
      const status = body.querySelector('#bkf-status').value;
      const res = body.querySelector('#bk-result');
      let rows;
      try {
        rows = await Api.get('/api/admin/bookings?date=' + date + (status ? '&status=' + status : ''));
      } catch (e) { res.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
      res.innerHTML = `
        <table class="tbl">
          <tr><th>学号</th><th>姓名</th><th>自习室</th><th>座位</th><th>日期</th><th>时段</th><th>状态</th><th>创建时间</th></tr>
          ${rows.map((b) => `
            <tr><td>${esc(b.student_id)}</td><td>${esc(b.user_name)}</td><td>${esc(b.room_name)}</td>
            <td>${esc(b.seat_no)}</td><td>${esc(b.date)}</td><td>${esc(b.start_time)} - ${esc(b.end_time)}</td>
            <td><span class="badge ${({ expired: 'red', completed: 'gray', cancelled: 'gray' })[b.status] || 'blue'}">${BK_LABEL[b.status] || b.status}</span></td>
            <td>${esc(b.created_at)}</td></tr>`).join('') || '<tr><td colspan="8" class="empty">暂无预约记录</td></tr>'}
        </table>`;
    };
    body.querySelector('#bkf-query').onclick = load;
    await load();
  };

  function hourOpts(from, toExclusive, selected) {
    return Ui.hoursOptions(from, toExclusive)
      .map((o) => `<option value="${o.value}" ${o.value === selected ? 'selected' : ''}>${o.value}</option>`).join('');
  }

  await render();
};