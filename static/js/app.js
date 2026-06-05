// ── Modal helpers ──
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
function closeModalOverlay(e, id) { if (e.target.id === id) closeModal(id); }

// ── Фильтр по типу объекта ──
// 'all' — все объекты компании (без частников)
// 'cottage'/'hotel'/'apartment'/'employee' — компания + конкретный тип
// 'private' — все частники
function filterCottages(type, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  localStorage.setItem('cottageFilter', type);
  document.querySelectorAll('.cottage-card').forEach(card => {
    const isCompany = card.dataset.owner === 'company';
    let show = false;
    if (type === 'all')          show = isCompany;
    else if (type === 'private') show = card.dataset.owner === 'private';
    else                         show = isCompany && card.dataset.ptype === type;
    card.style.display = show ? '' : 'none';
  });
}

// Восстанавливаем фильтр после перезагрузки (по data-filter)
(function restoreCottageFilter() {
  const saved = localStorage.getItem('cottageFilter') || 'all';
  const btns  = Array.from(document.querySelectorAll('.filter-btn'));
  const order = ['all', 'cottage', 'hotel', 'apartment', 'employee', 'private'];
  const idx   = order.indexOf(saved);
  const btn   = idx >= 0 ? btns[idx] : btns[0];
  if (btn) filterCottages(saved, btn);
})();

// ── Excel дропдаун ──
function toggleExcelMenu(e) {
  e.stopPropagation();
  const menu = document.getElementById('excel-menu');
  menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}
document.addEventListener('click', () => {
  const menu = document.getElementById('excel-menu');
  if (menu) menu.style.display = 'none';
});

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
function onOwnerToggle() {
  const ownerType = document.querySelector('input[name="owner_type"]:checked')?.value;
  const isPrivate = ownerType === 'Собственник';
  document.getElementById('owner-name-group').style.display     = isPrivate ? 'block' : 'none';
  document.getElementById('price-capacity-group').style.display  = isPrivate ? 'none'  : 'block';
  document.getElementById('contacts-group').style.display        = isPrivate ? 'block' : 'none';
}

function openAddCottage() {
  document.getElementById('cottage-modal-title').textContent = 'Новый объект';
  document.getElementById('cottage-id').value = '';
  document.getElementById('form-cottage').reset();
  document.getElementById('cottage-ptype').value   = 'Коттедж';
  document.getElementById('owner-company').checked = true;
  onOwnerToggle();
  openModal('modal-add-cottage');
}

function editCottage(id, name, capacity, price, desc, ownerType, ownerName, contacts, propertyType) {
  document.getElementById('cottage-modal-title').textContent = 'Редактировать';
  document.getElementById('cottage-id').value              = id;
  document.getElementById('cottage-name').value            = name;
  document.getElementById('cottage-capacity').value        = capacity;
  document.getElementById('cottage-price').value           = price;
  document.getElementById('cottage-description').value     = desc;
  document.getElementById('cottage-contacts').value        = contacts || '';
  document.getElementById('cottage-owner-name').value      = ownerName || '';
  document.getElementById('cottage-ptype').value           = propertyType || 'Коттедж';
  document.getElementById('owner-company').checked         = ownerType !== 'Собственник';
  document.getElementById('owner-private').checked         = ownerType === 'Собственник';
  onOwnerToggle();
  openModal('modal-add-cottage');
}

async function submitCottage(e) {
  e.preventDefault();
  const id = document.getElementById('cottage-id').value;
  const ownerType    = document.querySelector('input[name="owner_type"]:checked')?.value || 'Компания';
  const propertyType = document.getElementById('cottage-ptype').value || 'Коттедж';
  const isPrivate    = ownerType === 'Собственник';
  const body = {
    name:          document.getElementById('cottage-name').value.trim(),
    capacity:      isPrivate ? 0 : (document.getElementById('cottage-capacity').value || 0),
    price_per_day: isPrivate ? 0 : (document.getElementById('cottage-price').value || 0),
    description:   document.getElementById('cottage-description').value.trim(),
    contacts:      isPrivate ? document.getElementById('cottage-contacts').value.trim() : '',
    owner_type:    ownerType,
    property_type: propertyType,
    owner_name:    isPrivate ? document.getElementById('cottage-owner-name').value.trim() : '',
  };
  const url    = id ? `/cottages/${id}` : '/cottages';
  const method = id ? 'PUT' : 'POST';
  const res = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  if (!res.ok) { const d = await res.json(); showToast(d.error, 'error'); return; }
  showToast(id ? 'Объект обновлён' : 'Объект добавлен', 'success');
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
let fpCheckin = null, fpCheckout = null;
let occupiedRanges = [];

// ISO YYYY-MM-DD
function isoDate(d) {
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}
// Из {from: заезд, to: выезд} делаем занятые НОЧИ [заезд .. выезд-1]
function occupiedNights(ranges) {
  return ranges.map(r => {
    const to = new Date(r.to + 'T00:00:00');
    to.setDate(to.getDate() - 1);
    return { from: r.from, to: isoDate(to) };
  });
}

async function openBookingModal(cottageId, name, capacity, price) {
  bookingPrice = price;
  document.getElementById('booking-cottage-id').value          = cottageId;
  document.getElementById('booking-cottage-name').textContent  = name;
  document.getElementById('booking-max-guests').value          = capacity;
  document.getElementById('booking-guests').max                = capacity;
  document.getElementById('booking-capacity-hint').textContent = `Максимум: ${capacity} чел.`;
  document.getElementById('form-booking').reset();
  document.getElementById('booking-total-block').style.display = 'none';

  // Загружаем занятые даты
  occupiedRanges = [];
  try {
    const r = await fetch(`/cottages/${cottageId}/booked-ranges`);
    occupiedRanges = await r.json();
  } catch (_) {}

  initBookingCalendars();
  showBusyHint();
  openModal('modal-booking');
}

function showBusyHint() {
  const hint = document.getElementById('booking-busy-hint');
  if (!hint) return;
  if (!occupiedRanges.length) { hint.style.display = 'none'; return; }
  const fmt = s => { const [y,m,d]=s.split('-'); return `${d}/${m}/${y}`; };
  hint.innerHTML = '🔴 Занято: ' + occupiedRanges.map(r => `${fmt(r.from)}–${fmt(r.to)}`).join(', ');
  hint.style.display = 'block';
}

function initBookingCalendars() {
  const disable = occupiedNights(occupiedRanges);
  const common = {
    dateFormat: 'Y-m-d',
    altInput: true,
    altFormat: 'd/m/Y',
    locale: 'ru',
    disable: disable,
    onChange: calcBookingTotal,
  };
  if (fpCheckin)  fpCheckin.destroy();
  if (fpCheckout) fpCheckout.destroy();
  fpCheckin  = flatpickr('#booking-checkin',  { ...common, minDate: 'today',
    onChange: (sel) => { if (sel[0]) fpCheckout.set('minDate', sel[0]); calcBookingTotal(); } });
  fpCheckout = flatpickr('#booking-checkout', { ...common });
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

// Проверка пересечения с занятыми ночами на клиенте
function rangeOverlaps(ci, co) {
  const a1 = new Date(ci), a2 = new Date(co);
  return occupiedRanges.some(r => {
    const b1 = new Date(r.from), b2 = new Date(r.to);
    return a1 < b2 && a2 > b1;
  });
}

async function submitBooking(e) {
  e.preventDefault();
  const rate = parseFloat(document.getElementById('booking-rate').value);
  if (!rate || rate <= 0) { showToast('Введите курс доллара', 'error'); return; }
  const ci = document.getElementById('booking-checkin').value;
  const co = document.getElementById('booking-checkout').value;
  if (rangeOverlaps(ci, co)) { showToast('❌ Эти даты уже заняты!', 'error'); return; }
  const body = {
    cottage_id: document.getElementById('booking-cottage-id').value,
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
  showToast('Бронь создана!', 'success');
  closeModal('modal-booking');
  setTimeout(() => location.reload(), 600);  // обновить счётчик броней
}
