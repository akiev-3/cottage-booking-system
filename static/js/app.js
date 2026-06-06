// ── Modal helpers ──
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
function closeModalOverlay(e, id) { if (e.target.id === id) closeModal(id); }

// ── Drag-and-drop сортировка строк ──
function renumberRows(tbody) {
  let n = 0;
  tbody.querySelectorAll('tr').forEach(tr => {
    if (tr.style.display === 'none') return;
    const cell = tr.querySelector('td.num-col');
    if (cell) cell.textContent = ++n;
  });
}

// Снимаем остаточные inline-стили, которые SortableJS оставляет на <tr>
// после нескольких перетаскиваний (из-за чего появляются пустые «разрывы»).
function _clearRowTransforms(tbody) {
  tbody.querySelectorAll('tr').forEach(tr => {
    tr.style.transform  = '';
    tr.style.transition = '';
  });
}

// ── Режим изменения порядка ──
// По умолчанию строки зафиксированы (перетаскивание выключено). Пользователь
// жмёт «Изменить порядок», двигает строки, затем «Сохранить» — все изменения
// уходят разом. «Отмена» возвращает прежний порядок.
let _sortables   = [];
let _reorderMode = false;
const _dirtyTbodies = new Set();

function initSortable() {
  if (typeof Sortable === 'undefined') return;
  _sortables = [];
  document.querySelectorAll('tbody.sortable-rows').forEach(tbody => {
    const s = Sortable.create(tbody, {
      animation: 0,                 // без анимации: у <tr> остаются «застрявшие» transform → разрывы
      handle: 'td',                 // тянуть за любую ячейку
      filter: '.row-actions, button, a, input',  // кроме кнопок
      preventOnFilter: false,
      disabled: true,               // включается только в режиме редактирования
      onEnd: () => { _clearRowTransforms(tbody); renumberRows(tbody); _dirtyTbodies.add(tbody); }
    });
    _sortables.push(s);
  });
}
document.addEventListener('DOMContentLoaded', initSortable);

function enterReorder() {
  _reorderMode = true;
  _dirtyTbodies.clear();
  _sortables.forEach(s => s.option('disabled', false));
  document.body.classList.add('reorder-mode');
  _updateReorderUI();
}

function cancelReorder() {
  if (_dirtyTbodies.size) {        // были перемещения — откатываем перезагрузкой
    _saveReorderScroll();
    location.reload();
    return;
  }
  _reorderMode = false;
  _sortables.forEach(s => s.option('disabled', true));
  document.body.classList.remove('reorder-mode');
  _updateReorderUI();
}

async function saveReorder() {
  const dirty = Array.from(_dirtyTbodies);
  if (!dirty.length) { cancelReorder(); showToast('Изменений нет'); return; }
  for (const tbody of dirty) {
    const url = tbody.dataset.reorder;
    const ids = Array.from(tbody.querySelectorAll('tr'))
                     .map(tr => (tr.id || '').replace('card-', ''))
                     .filter(Boolean);
    try {
      const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ ids }) });
      if (!res.ok) throw new Error();
    } catch (_) { showToast('Не удалось сохранить порядок', 'error'); return; }
  }
  showToast('Порядок сохранён', 'success');
  _saveReorderScroll();
  setTimeout(() => location.reload(), 400);
}

function _updateReorderUI() {
  const toggle = document.getElementById('reorder-toggle');
  const bar    = document.getElementById('reorder-bar');
  if (toggle) toggle.style.display = _reorderMode ? 'none' : '';
  if (bar)    bar.style.display    = _reorderMode ? 'flex' : 'none';
}

function _saveReorderScroll() {
  try { sessionStorage.setItem('reorderScroll', String(window.scrollY)); } catch (_) {}
}

// Восстановление прокрутки после сохранения/отмены порядка
document.addEventListener('DOMContentLoaded', () => {
  let sy = null;
  try { sy = sessionStorage.getItem('reorderScroll'); } catch (_) {}
  if (sy !== null) {
    try { sessionStorage.removeItem('reorderScroll'); } catch (_) {}
    window.scrollTo(0, parseInt(sy, 10) || 0);
  }
});

// ── Восстановление базы из файла бэкапа (admin) ──
async function restoreBackup(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  if (!confirm('⚠️ ВНИМАНИЕ!\n\nВосстановление ПОЛНОСТЬЮ заменит все текущие данные (объекты, брони, услуги, курс) данными из файла.\n\nТекущие данные будут удалены без возможности отмены. Продолжить?')) {
    input.value = ''; return;
  }
  if (!confirm('Точно восстановить базу из этого файла? Это последнее предупреждение.')) {
    input.value = ''; return;
  }
  const fd = new FormData();
  fd.append('file', file);
  showToast('Восстановление базы…');
  try {
    const res  = await fetch('/backup/restore', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || !data.ok) { showToast('Ошибка: ' + (data.error || res.status), 'error'); input.value = ''; return; }
    showToast(data.message || 'База восстановлена', 'success');
    setTimeout(() => location.reload(), 1400);
  } catch (e) {
    showToast('Ошибка сети', 'error');
  }
  input.value = '';
}

// ── Демо-данные ──
async function clearDemo() {
  if (!confirm('Удалить все демо-брони и демо-заказы?')) return;
  showToast('Удаление…');
  try {
    const res  = await fetch('/clear-demo', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.ok) { showToast('Ошибка: ' + (data.error || res.status), 'error'); return; }
    showToast(data.message, 'success');
    setTimeout(() => location.reload(), 1000);
  } catch (e) { showToast('Ошибка сети', 'error'); }
}

async function seedDemo() {
  if (!confirm('Сгенерировать тестовые брони и заказы услуг для всех объектов компании?')) return;
  showToast('Генерация данных…');
  try {
    const res  = await fetch('/seed-demo', { method: 'POST' });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      showToast('Ошибка: ' + (data.error || res.status), 'error');
      console.error('seed error:', data);
      return;
    }
    showToast(data.message || 'Готово!', 'success');
    setTimeout(() => location.reload(), 1500);
  } catch (e) {
    showToast('Ошибка сети', 'error');
    console.error(e);
  }
}

// ── Переключение вида (отдельная таблица на каждый тип) ──
const VIEW_ORDER = ['all', 'cottage', 'hotel', 'apartment', 'employee', 'private'];
function showView(type, btn) {
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  VIEW_ORDER.forEach(v => {
    const el = document.getElementById('view-' + v);
    if (el) el.style.display = (v === type) ? '' : 'none';
  });
  localStorage.setItem('cottageFilter', type);
}

// Восстанавливаем выбранный вид после перезагрузки
(function restoreView() {
  const saved = localStorage.getItem('cottageFilter') || 'all';
  const idx   = VIEW_ORDER.indexOf(saved);
  const btns  = Array.from(document.querySelectorAll('.filter-btn'));
  const btn   = idx >= 0 ? btns[idx] : btns[0];
  showView(idx >= 0 ? saved : 'all', btn);
})();

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
  const ptype     = document.getElementById('cottage-ptype').value;
  const isPrivate = ownerType === 'Собственник';
  const isCottage = ptype === 'Коттедж';
  document.getElementById('owner-name-group').style.display    = isPrivate ? 'block' : 'none';
  document.getElementById('price-capacity-group').style.display = isPrivate ? 'none'  : 'block';
  document.getElementById('contacts-group').style.display       = isPrivate ? 'block' : 'none';
  // Размер коттеджа — только для коттеджей компании
  document.getElementById('cottage-size-group').style.display   = (!isPrivate && isCottage) ? 'block' : 'none';
  // Этаж — для квартир / номеров отеля / сотрудников (не коттедж, не собственник)
  document.getElementById('floor-group').style.display          = (!isPrivate && !isCottage) ? 'block' : 'none';
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

function editCottage(id, name, capacity, price, desc, ownerType, ownerName, contacts, propertyType, size, rooms, floor) {
  document.getElementById('cottage-modal-title').textContent = 'Редактировать';
  document.getElementById('cottage-id').value              = id;
  document.getElementById('cottage-name').value            = name;
  document.getElementById('cottage-capacity').value        = capacity;
  document.getElementById('cottage-price').value           = price;
  document.getElementById('cottage-description').value     = desc;
  document.getElementById('cottage-contacts').value        = contacts || '';
  document.getElementById('cottage-owner-name').value      = ownerName || '';
  document.getElementById('cottage-ptype').value           = propertyType || 'Коттедж';
  document.getElementById('cottage-size').value            = size || 'Большой';
  document.getElementById('cottage-rooms').value           = rooms || '';
  document.getElementById('cottage-floor').value           = floor || '';
  document.getElementById('owner-company').checked         = ownerType !== 'Собственник';
  document.getElementById('owner-private').checked         = ownerType === 'Собственник';
  onOwnerToggle();
  openModal('modal-add-cottage');
}

async function submitCottage(e) {
  e.preventDefault();
  const id = document.getElementById('cottage-id').value;
  if (!document.getElementById('cottage-name').value.trim()) {
    showToast('Введите название объекта', 'error'); return;
  }
  const ownerType    = document.querySelector('input[name="owner_type"]:checked')?.value || 'Компания';
  const propertyType = document.getElementById('cottage-ptype').value || 'Коттедж';
  const isPrivate    = ownerType === 'Собственник';
  const isCottage    = propertyType === 'Коттедж';
  const body = {
    name:          document.getElementById('cottage-name').value.trim(),
    capacity:      isPrivate ? 0 : (document.getElementById('cottage-capacity').value || 0),
    price_per_day: isPrivate ? 0 : (document.getElementById('cottage-price').value || 0),
    description:   document.getElementById('cottage-description').value.trim(),
    contacts:      isPrivate ? document.getElementById('cottage-contacts').value.trim() : '',
    owner_type:    ownerType,
    property_type: propertyType,
    owner_name:    isPrivate ? document.getElementById('cottage-owner-name').value.trim() : '',
    cottage_size:  (!isPrivate && isCottage) ? document.getElementById('cottage-size').value : '',
    rooms:         isPrivate ? 0 : (document.getElementById('cottage-rooms').value || 0),
    floor:         (!isPrivate && !isCottage) ? document.getElementById('cottage-floor').value.trim() : '',
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
  if (!confirm('Удалить объект и все его брони?')) return;
  await fetch(`/cottages/${id}`, { method: 'DELETE' });
  showToast('Объект удалён');
  setTimeout(() => location.reload(), 500);
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

const EXTRA_FEE_TYPES = ['Коттедж', 'Номер отеля', 'Квартира'];

async function openBookingModal(cottageId, name, capacity, price, propertyType) {
  bookingPrice = price;
  document.getElementById('booking-cottage-id').value          = cottageId;
  document.getElementById('booking-cottage-name').textContent  = name;
  document.getElementById('booking-max-guests').value          = capacity;
  document.getElementById('booking-guests').max                = capacity;
  document.getElementById('booking-capacity-hint').textContent = `Максимум: ${capacity} чел.`;
  document.getElementById('form-booking').reset();
  document.getElementById('booking-total-block').style.display = 'none';
  // Показать поле доп. гостей только для коттеджей, номеров и квартир
  const extraGroup = document.getElementById('booking-extra-group');
  if (extraGroup) extraGroup.style.display = EXTRA_FEE_TYPES.includes(propertyType) ? '' : 'none';

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
  // Текст-подсказку не показываем — занятые даты видны в календаре зачёркнутыми
  const hint = document.getElementById('booking-busy-hint');
  if (hint) hint.style.display = 'none';
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
  const ci         = document.getElementById('booking-checkin').value;
  const co         = document.getElementById('booking-checkout').value;
  const discount   = parseFloat(document.getElementById('booking-discount').value) || 0;   // сомы
  const extraNight = parseFloat(document.getElementById('booking-extra').value) || 0;       // сомы
  if (!ci || !co) return;
  const nights      = Math.round((new Date(co) - new Date(ci)) / 86400000);
  const block       = document.getElementById('booking-total-block');
  if (nights <= 0)  { block.style.display = 'none'; return; }
  const extraTotal  = extraNight * nights;
  const totalBefore = nights * bookingPrice + extraTotal;        // сомы
  const totalSom    = Math.max(0, totalBefore - discount);       // сомы
  const totalUsd    = RATE ? Math.round(totalSom / RATE) : 0;    // $ по глобальному курсу
  document.getElementById('booking-total-usd').textContent   = `${totalSom.toLocaleString('ru-RU')} сом`;
  document.getElementById('booking-total-tenge').textContent = RATE ? `≈ $${totalUsd.toLocaleString('ru-RU')}` : '';
  document.getElementById('booking-nights').textContent      = `${nights} ночей`;
  const discLine = document.getElementById('booking-discount-line');
  if (discount > 0) {
    discLine.textContent = `Скидка -${discount.toLocaleString('ru-RU')} сом · было ${totalBefore.toLocaleString('ru-RU')} сом`;
    discLine.style.display = 'block';
  } else {
    discLine.style.display = 'none';
  }
  const extraLine = document.getElementById('booking-extra-line');
  if (extraTotal > 0) {
    extraLine.textContent = `Доп. гости +${extraNight.toLocaleString('ru-RU')} сом/ночь × ${nights} = ${extraTotal.toLocaleString('ru-RU')} сом`;
    extraLine.style.display = 'block';
  } else {
    extraLine.style.display = 'none';
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
  const ci = document.getElementById('booking-checkin').value;
  const co = document.getElementById('booking-checkout').value;
  if (!ci || !co) { showToast('Выберите даты заезда и выезда', 'error'); return; }
  if (new Date(co) <= new Date(ci)) { showToast('Дата выезда должна быть позже заезда', 'error'); return; }
  if (rangeOverlaps(ci, co)) { showToast('❌ Эти даты уже заняты!', 'error'); return; }
  const body = {
    cottage_id: document.getElementById('booking-cottage-id').value,
    guest_name: document.getElementById('booking-guest-name').value.trim(),
    check_in:   ci,
    check_out:  co,
    guests:     document.getElementById('booking-guests').value,
    discount:        parseFloat(document.getElementById('booking-discount').value) || 0,
    deposit_paid:    parseFloat(document.getElementById('booking-deposit').value) || 0,
    extra_per_night: parseFloat(document.getElementById('booking-extra').value) || 0,
    notes:           document.getElementById('booking-notes').value.trim(),
  };
  const res  = await fetch('/bookings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) { showToast(data.error, 'error'); return; }
  showToast('Бронь создана!', 'success');
  closeModal('modal-booking');
  setTimeout(() => location.reload(), 600);  // обновить счётчик броней
}

// ── Глобальный курс доллара (редактирование на главном экране) ──
function openRateEdit() {
  const disp = document.getElementById('rate-display');
  const edit = document.getElementById('rate-edit');
  if (!edit) return;
  disp.style.display = 'none';
  edit.style.display = 'inline-flex';
  const inp = document.getElementById('rate-input');
  inp.value = Math.round(RATE);
  inp.focus(); inp.select();
}
function cancelRateEdit() {
  document.getElementById('rate-display').style.display = 'inline-flex';
  document.getElementById('rate-edit').style.display = 'none';
}
async function saveRate() {
  const val = parseFloat(document.getElementById('rate-input').value);
  if (!val || val <= 0) { showToast('Введите курс больше 0', 'error'); return; }
  try {
    const res  = await fetch('/settings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ rate: val }) });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Ошибка', 'error'); return; }
    RATE = data.rate;
    document.getElementById('rate-value').textContent = Math.round(data.rate);
    cancelRateEdit();
    showToast('Курс обновлён', 'success');
  } catch (_) { showToast('Ошибка сети', 'error'); }
}
