/* 视图：我的预约 —— 当前预约（剩余时间/续约/离座/取消）+ 历史记录 */
var Views = window.Views;

const fmtLeft = (min) => {
  if (min == null) return '';
  if (min <= 0) return '<span class="badge orange">已到期</span>';
  const h = Math.floor(min / 60), m = min % 60;
  return `<span class="badge blue">剩余 ${h > 0 ? h + ' 小时 ' : ''}${m} 分钟</span>`;
};

Views.mybookings = async function () {
  const root = document.getElementById('view');
  root.innerHTML = '<div class="spin">加载中…</div>';
  let list;
  try {
    list = await Api.get('/api/my-bookings');
  } catch (e) {
    root.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  const active = list.filter((b) => b.status === 'reserved' || b.status === 'occupied');
  const history = list.filter((b) => !(b.status === 'reserved' || b.status === 'occupied'));

  root.innerHTML = `
    <h1 class="page-title">我的预约</h1>
    <div class="card">
      <div class="section-title">当前预约（${active.length}）</div>
      ${active.length ? active.map(renderActive).join('') : '<div class="empty">暂无进行中的预约，去 <a href="#/rooms">选座预约</a></div>'}
      <div class="section-title" style="margin-top:26px">历史记录（${history.length}）</div>
      <table class="tbl">
        <tr><th>自习室</th><th>座位</th><th>日期</th><th>时段</th><th>时长</th><th>状态</th></tr>
        ${history.map((b) => `
          <tr><td>${esc(b.room_name)}</td><td>${esc(b.seat_no)}</td><td>${esc(b.date)}</td>
          <td>${esc(b.start_time)} - ${esc(b.end_time)}</td><td>${b.hours} 小时</td>
          <td><span class="badge ${({ expired: 'red', completed: 'gray', cancelled: 'gray' })[b.status] || 'gray'}">${BK_LABEL[b.status] || b.status}</span></td></tr>`).join('') || '<tr><td colspan="6" class="empty">暂无历史记录</td></tr>'}
      </table>
    </div>`;

  function renderActive(b) {
    const canCancel = b.status === 'reserved';
    return `
      <div class="booking-item" data-id="${b.id}">
        <div class="info">
          <strong>${esc(b.room_name)} · ${esc(b.seat_no)}</strong>
          <span class="badge ${b.status === 'reserved' ? 'blue' : 'orange'}" style="margin-left:8px">${BK_LABEL[b.status]}</span>
          <div class="sub">${esc(b.date)} ${esc(b.start_time)} - ${esc(b.end_time)}（${b.hours} 小时） ${fmtLeft(b.minutes_left)}</div>
        </div>
        <div class="ops">
          <button class="btn sm" data-act="renew">续约</button>
          <button class="btn sm" data-act="leave">离座</button>
          ${canCancel ? '<button class="btn sm danger" data-act="cancel">取消</button>' : ''}
        </div>
      </div>`;
  }

  const doLeave = async (b) => {
    try {
      await Api.post(`/api/bookings/${b.id}/leave`, {});
      Ui.toast('已离座，座位已释放', 'success');
      Views.mybookings();
    } catch (e) { Ui.toast(e.message, 'error'); }
  };

  root.querySelectorAll('[data-act]').forEach((btn) => {
    const b = list.find((x) => x.id === Number(btn.closest('.booking-item').dataset.id));
    btn.onclick = () => {
      const act = btn.dataset.act;
      if (act === 'leave') {
        Ui.confirm('离座', `确定离开 <strong>${esc(b.room_name)} · ${esc(b.seat_no)}</strong> 吗？座位将立即释放给其他同学。`,
          () => doLeave(b));
      } else if (act === 'cancel') {
        Ui.confirm('取消预约', `将取消 <strong>${esc(b.room_name)} · ${esc(b.seat_no)}</strong> 的预约。`, async () => {
          try {
            await Api.post(`/api/bookings/${b.id}/cancel`, {});
            Ui.toast('预约已取消', 'success');
            Views.mybookings();
          } catch (e) { Ui.toast(e.message, 'error'); }
        });
      } else if (act === 'renew') {
        openRenewModal(b);
      }
    };
  });

  /* 续约：选择新结束时间（1 小时粒度）；续约后总时长 >4h 前端即拦截 */
  function openRenewModal(b) {
    const curEndHour = parseInt(b.end_time, 10);
    const modal = Ui.modal(`续约 · ${b.room_name} ${b.seat_no}`, `
      <div class="meta">当前时段：${esc(b.date)} ${esc(b.start_time)} - ${esc(b.end_time)}（${b.hours} 小时）</div>
      <div class="field"><label>新的结束时间</label><select id="rn-end"></select></div>
      <div class="hours-line" id="rn-hours"></div>
      <div class="err-text" id="rn-err"></div>
    `, {
      buttons: [
        { text: '取消', cls: 'btn muted' },
        { text: '确认续约', cls: 'btn', click: () => submit() },
      ],
    });
    const endSel = modal.box.querySelector('#rn-end');
    endSel.innerHTML = Ui.hoursOptions(curEndHour + 1, 23)
      .filter((o) => parseInt(o.value, 10) <= 22)
      .map((o) => `<option value="${o.value}">${o.value}</option>`).join('');
    const errEl = modal.box.querySelector('#rn-err');

    const refresh = () => {
      const line = modal.box.querySelector('#rn-hours');
      const total = hoursBetween(b.start_time, endSel.value);
      line.classList.add('show');
      if (total > 4) {
        line.style.display = 'none';
        errEl.textContent = '单次预约最长 4 小时，请缩短时间段或分段预约。';
      } else {
        line.textContent = `续约后总时长 ${total} 小时（${esc(b.start_time)} - ${endSel.value}）`;
        errEl.textContent = '';
        line.style.display = '';
      }
    };
    endSel.onchange = refresh;
    refresh();

    async function submit() {
      if (hoursBetween(b.start_time, endSel.value) > 4) {
        errEl.textContent = '单次预约最长 4 小时，请缩短时间段或分段预约。';
        return;
      }
      try {
        await Api.post(`/api/bookings/${b.id}/renew`, { new_end_time: endSel.value });
        Ui.toast('续约成功，座位状态已同步', 'success');
        Views.mybookings();
      } catch (e) {
        errEl.textContent = e.message;
      }
    }
  }
};