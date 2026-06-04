// ── Modal helpers ──
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
function closeModalOverlay(e, id) { if (e.target.id === id) closeModal(id); }

// ── Toast ──
function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  void t.offsetWidth;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3200);
}

// ── Cottage form ──
function toggleOwnerName() {
  const isPrivate = document.getElementById('owner-private').checked;
  document.getElementById('owner-name-group').style.display = isPrivate ? 'block' : 'none';
}

function openAddCottage() {
  document.getElementById('cottage-modal-title').textContent = 'Новый коттедж';
  document.getElementById('cottage-id').value = '';
  document.getElementById('form-cottage').reset();
  document.getElementById('owner-alma').checked = true;
  document.getElementById('owner-name-group').style.display = 'none';
  openModal('modal-add-cottage');
}

function editCottage(id, name, capacity, price, desc, ownerType, ownerName) {
  document.getElementById('cottage-modal-title').textContent = 'Редактировать коттедж';
  document.getElementById('cottage-id').value = id;
  document.getElementById('cottage-name').value = name;
  document.getElementById('cottage-capacity').value = capacity;
  document.getElementById('cottage-price').value = price;
  document.getElementById('cottage-description').value = desc;
  const isPrivate = ownerType === 'Собственник';
  document.getElementById('owner-alma').checked    = !isPrivate;
  document.getElementById('owner-private').checked = isPrivate;
  document.getElementById('cottage-owner-name').value = ownerName || '';
  document.getElementById('owner-name-group').style.display = isPrivate ? 'block' : 'none';
  openModal('modal-add-cottage');
}

async function submitCottage(e) {
  e.preventDefault();
  const id = document.getElementById('cottage-id').value;
  const ownerType = document.querySelector('input[name="owner_type"]:checked')?.value || 'Алма-Ата';
  const body = {
    name:          document.getElementById('cottage-name').value.trim(),
    capacity:      document.getElementById('cottage-capacity').value,
    price_per_day: document.getElementById('cottage-price').value,
    description:   document.getElementById('cottage-description').value.trim(),
    owner_type:    ownerType,
    owner_name:    ownerType === 'Собственник' ? document.getElementById('cottage-owner-name').value.trim() : '',
  };
  const url    = id ? `/cottages/${id}` : '/cottages';
  const method = id ? 'PUT' : 'POST';
  const res = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (!res.ok) { const d = await res.json(); showToast(d.error, 'error'); return; }
  showToast(id ? 'Коттедж обновлён' : 'Коттедж добавлен', 'success');
  closeModal('modal-add-cottage');
  setTimeout(() => location.reload(), 600);
}

async function deleteCottage(id) {
  if (!confirm('Удалить коттедж и все его брони?')) return;
  await fetch(`/cottages/${id}`, { method: 'DELETE' });
  document.getElementById(`card-${id}`)?.remove();
  showToast('Коттедж удалён');
}

// ── Booking modal ──
let bookingPrice = 0;

function openBookingModal(cottageId, name, capacity, price) {
  bookingPrice = price;
  document.getElementById('booking-cottage-id').value          = cottageId;
  document.getElementById('booking-cottage-name').textContent  = name;
  document.getElementById('booking-max-guests').value          = capacity;
  document.getElementById('booking-guests').max                = capacity;
  document.getElementById('booking-capacity-hint').textContent = `Максимум: ${capacity} чел.`;
  document.getElementById('form-booking').reset();
  document.getElementById('booking-total-block').style.display = 'none';
  openModal('modal-booking');
}

function calcBookingTotal() {
  const ci       = document.getElementById('booking-checkin').value;
  const co       = document.getElementById('booking-checkout').value;
  const rate     = parseFloat(document.getElementById('booking-rate').value);
  const discount = parseFloat(document.getElementById('booking-discount').value) || 0;
  if (!ci || !co || !rate) return;
  const nights      = Math.round((new Date(co) - new Date(ci)) / 86400000);
  const block       = document.getElementById('booking-total-block');
  if (nights <= 0)  { block.style.display = 'none'; return; }
  const totalBefore = nights * bookingPrice;
  const totalUsd    = Math.max(0, totalBefore - discount);
  const totalSom    = Math.round(totalUsd * rate);
  document.getElementById('booking-total-usd').textContent   = `$${totalUsd.toLocaleString('ru-RU')}`;
  document.getElementById('booking-total-tenge').textContent = `≈ ${totalSom.toLocaleString('ru-RU')} сом`;
  document.getElementById('booking-nights').textContent      = `${nights} ночей`;
  const discLine = document.getElementById('booking-discount-line');
  if (discount > 0) {
    discLine.textContent = `Скидка -$${discount} · было $${totalBefore.toLocaleString('ru-RU')}`;
    discLine.style.display = 'block';
  } else {
    discLine.style.display = 'none';
  }
  block.style.display = 'flex';
}

async function submitBooking(e) {
  e.preventDefault();
  const rate = parseFloat(document.getElementById('booking-rate').value);
  if (!rate || rate <= 0) { showToast('Введите курс доллара', 'error'); return; }
  const body = {
    cottage_id: document.getElementById('booking-cottage-id').value,
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
  showToast('Бронь создана!', 'success');
  closeModal('modal-booking');
}
