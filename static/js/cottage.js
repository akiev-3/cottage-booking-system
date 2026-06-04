function openModal(id) { document.getElementById(id).classList.add('open'); }
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
  const body = {
    cottage_id: COTTAGE_ID,
    guest_name: document.getElementById('booking-guest-name').value.trim(),
    check_in:   document.getElementById('booking-checkin').value,
    check_out:  document.getElementById('booking-checkout').value,
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
