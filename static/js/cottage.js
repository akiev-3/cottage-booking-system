function openModal(id) {
  document.getElementById(id).classList.add('open');
  if (id === 'modal-booking') showBusyHint();
}
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
function closeModalOverlay(e, id) { if (e.target.id === id) closeModal(id); }

function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = 'toast ' + type;
  void t.offsetWidth;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3200);
}

// ── Календарь с занятыми датами ──
function isoDate(d) {
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}
function occupiedNights(ranges) {
  return ranges.map(r => {
    const to = new Date(r.to + 'T00:00:00');
    to.setDate(to.getDate() - 1);
    return { from: r.from, to: isoDate(to) };
  });
}
function rangeOverlaps(ci, co) {
  const a1 = new Date(ci), a2 = new Date(co);
  return BOOKED_RANGES.some(r => {
    const b1 = new Date(r.from), b2 = new Date(r.to);
    return a1 < b2 && a2 > b1;
  });
}
function showBusyHint() {
  const hint = document.getElementById('booking-busy-hint');
  if (!hint) return;
  if (!BOOKED_RANGES.length) { hint.style.display = 'none'; return; }
  const fmt = s => { const [y,m,d]=s.split('-'); return `${d}/${m}/${y}`; };
  hint.innerHTML = '🔴 Занято: ' + BOOKED_RANGES.map(r => `${fmt(r.from)}–${fmt(r.to)}`).join(', ');
  hint.style.display = 'block';
}

let fpCheckin = null, fpCheckout = null;
document.addEventListener('DOMContentLoaded', () => {
  const disable = occupiedNights(BOOKED_RANGES);
  const common  = { dateFormat:'Y-m-d', altInput:true, altFormat:'d/m/Y', locale:'ru', disable, onChange: calcTotal };
  fpCheckin  = flatpickr('#booking-checkin',  { ...common, minDate:'today',
    onChange:(sel)=>{ if(sel[0]) fpCheckout.set('minDate', sel[0]); calcTotal(); } });
  fpCheckout = flatpickr('#booking-checkout', { ...common });
});

function calcTotal() {
  const ci       = document.getElementById('booking-checkin').value;
  const co       = document.getElementById('booking-checkout').value;
  const rate     = parseFloat(document.getElementById('booking-rate').value);
  const discount = parseFloat(document.getElementById('booking-discount').value) || 0;
  if (!ci || !co || !rate) return;
  const nights      = Math.round((new Date(co) - new Date(ci)) / 86400000);
  const block       = document.getElementById('total-block');
  if (nights <= 0)  { block.style.display = 'none'; return; }
  const totalBefore = nights * PRICE_PER_DAY;
  const totalUsd    = Math.max(0, totalBefore - discount);
  const totalSom    = Math.round(totalUsd * rate);
  document.getElementById('total-usd').textContent    = `$${totalUsd.toLocaleString('ru-RU')}`;
  document.getElementById('total-tenge').textContent  = `≈ ${totalSom.toLocaleString('ru-RU')} сом`;
  document.getElementById('total-nights').textContent = `${nights} ночей`;
  const discLine = document.getElementById('total-discount-line');
  if (discount > 0) {
    discLine.textContent = `Скидка -$${discount} · было $${totalBefore.toLocaleString('ru-RU')}`;
    discLine.style.display = 'block';
  } else {
    discLine.style.display = 'none';
  }
  block.style.display = 'flex';
}

async function submitBookingPage(e) {
  e.preventDefault();
  const rate = parseFloat(document.getElementById('booking-rate').value);
  if (!rate || rate <= 0) { showToast('Введите курс доллара', 'error'); return; }
  const ci = document.getElementById('booking-checkin').value;
  const co = document.getElementById('booking-checkout').value;
  if (!ci || !co) { showToast('Выберите даты заезда и выезда', 'error'); return; }
  if (new Date(co) <= new Date(ci)) { showToast('Дата выезда должна быть позже заезда', 'error'); return; }
  if (rangeOverlaps(ci, co)) { showToast('❌ Эти даты уже заняты!', 'error'); return; }
  const body = {
    cottage_id: COTTAGE_ID,
    guest_name: document.getElementById('booking-guest-name').value.trim(),
    check_in:   ci,
    check_out:  co,
    guests:     document.getElementById('booking-guests').value,
    rate,
    discount:   parseFloat(document.getElementById('booking-discount').value) || 0,
    notes:      document.getElementById('booking-notes').value.trim(),
  };
  const res  = await fetch('/bookings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) { showToast(data.error, 'error'); return; }
  showToast('Бронь добавлена!', 'success');
  closeModal('modal-booking');
  setTimeout(() => location.reload(), 700);
}

async function deleteBooking(id) {
  if (!confirm('Удалить бронь?')) return;
  await fetch(`/bookings/${id}`, { method: 'DELETE' });
  document.getElementById(`row-${id}`)?.remove();
  showToast('Бронь удалена');
}
