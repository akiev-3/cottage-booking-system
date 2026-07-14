// ── Русская локаль календаря (зашита в код, без внешнего CDN) ──
const FP_RU = {
  weekdays: {
    shorthand: ["Вс","Пн","Вт","Ср","Чт","Пт","Сб"],
    longhand: ["Воскресенье","Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"],
  },
  months: {
    shorthand: ["Янв","Фев","Мар","Апр","Май","Июн","Июл","Авг","Сен","Окт","Ноя","Дек"],
    longhand: ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
  },
  firstDayOfWeek: 1,
  rangeSeparator: " — ",
  ordinal: function () { return ""; },
};
if (typeof flatpickr !== 'undefined') flatpickr.localize(FP_RU);

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
let excludeRange = null;   // при редактировании — диапазон самой брони (не считается занятым)
function activeRanges() {
  if (!excludeRange) return BOOKED_RANGES;
  // У объекта брони не пересекаются → дата заезда уникальна. Исключаем по ней,
  // а не по точному диапазону (его конец «плавает» из-за позднего выезда).
  return BOOKED_RANGES.filter(r => r.from !== excludeRange.from);
}
function rangeOverlaps(ci, co) {
  const a1 = new Date(ci), a2 = new Date(co);
  return activeRanges().some(r => {
    const b1 = new Date(r.from), b2 = new Date(r.to);
    return a1 <= b2 && a2 > b1;  // a1<=b2: день выезда тоже считается занятым
  });
}
function showBusyHint() {
  const hint = document.getElementById('booking-busy-hint');
  if (hint) hint.style.display = 'none';
}

// ── Быстрое повторное бронирование ──
let _quickbook = null;
let _lastBookingBody = null;

function fmtDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

(function initQuickbook() {
  try {
    const raw = sessionStorage.getItem('quickbook');
    if (!raw) return;
    _quickbook = JSON.parse(raw);
    document.addEventListener('DOMContentLoaded', () => {
      const banner = document.getElementById('quickbook-banner');
      const text   = document.getElementById('quickbook-text');
      if (!banner || !text) return;
      text.innerHTML = `Быстрое бронирование для <b>${_quickbook.guest_name || 'гостя'}</b> · ${fmtDate(_quickbook.check_in)} — ${fmtDate(_quickbook.check_out)}`;
      banner.style.display = 'flex';
    });
  } catch (_) { sessionStorage.removeItem('quickbook'); }
})();

function dismissQuickbook() {
  _quickbook = null;
  sessionStorage.removeItem('quickbook');
  const b = document.getElementById('quickbook-banner');
  if (b) b.style.display = 'none';
}

function showBookingSuccessPanel(guestName, ci, co) {
  document.getElementById('form-booking').style.display = 'none';
  const panel = document.getElementById('booking-success-panel');
  if (panel) panel.style.display = 'block';
  const nameEl = document.getElementById('booking-success-name');
  const infoEl = document.getElementById('booking-success-info');
  if (nameEl) nameEl.textContent = guestName || 'гостя';
  if (infoEl) infoEl.textContent = `${guestName} · ${fmtDate(ci)} — ${fmtDate(co)}`;
}

function closeBookingDone() {
  closeModal('modal-booking');
  location.reload();
}

function addAnotherBooking() {
  if (_lastBookingBody) {
    sessionStorage.setItem('quickbook', JSON.stringify(_lastBookingBody));
  }
  // На странице коттеджа "ещё объект" = переход на главную для выбора другого объекта
  window.location.href = '/';
}

let fpCheckin = null, fpCheckout = null;
let _editPrice = null; // исходная цена/ночь для режима редактирования; null = новая бронь
function initCalendars(allowPast) {
  const disableIn  = activeRanges();  // включает день выезда — на него нельзя заезжать
  // Для выезда не блокируем первый день соседней брони — выезд в день чужого заезда допустим
  const disableOut = activeRanges().map(r => {
    const from = new Date(r.from + 'T00:00:00'); from.setDate(from.getDate() + 1);
    const to   = new Date(r.to   + 'T00:00:00'); to.setDate(to.getDate() - 1);
    return { from: isoDate(from), to: isoDate(to) };
  }).filter(r => r.from <= r.to);
  const base = { dateFormat:'Y-m-d', altInput:true, altFormat:'d/m/Y', locale:FP_RU, onChange: calcTotal };
  if (fpCheckin)  fpCheckin.destroy();
  if (fpCheckout) fpCheckout.destroy();
  fpCheckin  = flatpickr('#booking-checkin',  { ...base, disable: disableIn, minDate: allowPast ? null : 'today',
    onChange:(sel)=>{ if(sel[0]){ const m=new Date(sel[0]); m.setDate(m.getDate()+2); fpCheckout.set('minDate', m); } calcTotal(); } });
  fpCheckout = flatpickr('#booking-checkout', { ...base, disable: disableOut });
}
let fpDepositDate = null, fpBalanceDate = null;
document.addEventListener('DOMContentLoaded', () => {
  initCalendars(false);
  const pdOpts = { dateFormat:'Y-m-d', altInput:true, altFormat:'d/m/Y', locale:FP_RU };
  fpDepositDate = flatpickr('#booking-deposit-date', pdOpts);
  fpBalanceDate = flatpickr('#booking-balance-date', pdOpts);
});

// Показать/скрыть поле доп. гостей в зависимости от типа объекта
function applyExtraFieldVisibility() {
  const group = document.getElementById('booking-extra-group');
  if (group) group.style.display = (typeof EXTRA_FEE_TYPES !== 'undefined' && EXTRA_FEE_TYPES.includes(PROPERTY_TYPE)) ? '' : 'none';
}

// Подсказка под полем гостей (лимит проверяется в submitBookingPage, не нативно)
function updateGuestLimit() {
  const hint  = document.getElementById('booking-capacity-hint');
  if (!hint) return;
  const extra = parseFloat(document.getElementById('booking-extra').value) || 0;
  hint.textContent = extra > 0
    ? 'Доплата за доп. гостей включена'
    : `Максимум: ${MAX_GUESTS} чел. — больше можно с доплатой`;
}

// Открыть форму создания
function openCreateBooking() {
  // Сброс к форме (если показана панель успеха)
  document.getElementById('form-booking').style.display = '';
  const sp = document.getElementById('booking-success-panel');
  if (sp) sp.style.display = 'none';

  excludeRange = null;
  _editPrice = null;
  document.getElementById('form-booking').reset();
  document.getElementById('booking-id').value = '';
  document.getElementById('booking-modal-title').textContent = 'Новая бронь';
  document.getElementById('booking-submit-btn').textContent  = 'Забронировать';
  document.getElementById('total-block').style.display = 'none';
  applyExtraFieldVisibility();
  initCalendars(false);

  if (fpDepositDate) fpDepositDate.clear();
  if (fpBalanceDate) fpBalanceDate.clear();

  // Предзаполнение из быстрого бронирования
  if (_quickbook) {
    document.getElementById('booking-guest-name').value = _quickbook.guest_name  || '';
    document.getElementById('booking-guests').value     = _quickbook.guests       || '';
    document.getElementById('booking-discount').value   = _quickbook.discount     || '';
    document.getElementById('booking-deposit').value    = _quickbook.deposit_paid || '';
    document.getElementById('booking-deposit-type').value = _quickbook.deposit_payment_type || '';
    document.getElementById('booking-payment').value    = _quickbook.payment_type || '';
    document.getElementById('booking-notes').value      = _quickbook.notes        || '';
    document.getElementById('booking-early-checkin').checked = !!_quickbook.early_checkin;
    document.getElementById('booking-late-checkout').checked = !!_quickbook.late_checkout;
    if (fpCheckin  && _quickbook.check_in)  fpCheckin.setDate(_quickbook.check_in, false);
    if (fpCheckout && _quickbook.check_out) {
      if (_quickbook.check_in) {
        const m = new Date(_quickbook.check_in + 'T00:00:00');
        m.setDate(m.getDate() + 2);
        fpCheckout.set('minDate', m);
      }
      fpCheckout.setDate(_quickbook.check_out, false);
    }
    calcTotal();
  } else {
    if (fpCheckin)  fpCheckin.clear();
    if (fpCheckout) fpCheckout.clear();
  }

  updateGuestLimit();
  openModal('modal-booking');
}

// Открыть форму редактирования
function editBooking(id, b) {
  excludeRange = { from: b.check_in, to: b.check_out };
  // Восстанавливаем исходную цену из сохранённых данных, чтобы preview не пересчитывался по текущей цене
  const _on = b.nights || 0;
  const _epn = b.extra_per_night || 0;
  const _elf = b.early_late_fee || 0;
  const _tbd = b.total_before_discount || 0;
  const _derived = (_on > 0 && _tbd > 0) ? (_tbd - _epn * _on - _elf) / _on : 0;
  _editPrice = _derived > 0 ? _derived : null;
  document.getElementById('booking-id').value         = id;
  document.getElementById('booking-modal-title').textContent = 'Редактировать бронь';
  document.getElementById('booking-submit-btn').textContent  = 'Сохранить';
  document.getElementById('booking-guest-name').value = b.guest_name || '';
  document.getElementById('booking-guests').value     = b.guests || '';
  document.getElementById('booking-discount').value   = b.discount || '';
  document.getElementById('booking-deposit').value    = b.deposit_paid || '';
  // extra_per_night хранится как суммарная надбавка/сутки → показываем ставку за 1 гостя
  const _eg = Math.max(1, (b.guests || 0) - MAX_GUESTS);
  document.getElementById('booking-extra').value      = b.extra_per_night ? Math.round(b.extra_per_night / _eg) : '';
  document.getElementById('booking-early-checkin').checked = !!b.early_checkin;
  document.getElementById('booking-late-checkout').checked = !!b.late_checkout;
  document.getElementById('booking-deposit-type').value    = b.deposit_payment_type || '';
  document.getElementById('booking-payment').value         = b.payment_type || '';
  if (fpDepositDate) fpDepositDate.setDate(b.deposit_date || null, false);
  if (fpBalanceDate) fpBalanceDate.setDate(b.balance_date || null, false);
  document.getElementById('booking-notes').value      = b.notes || '';
  applyExtraFieldVisibility();
  updateGuestLimit();
  initCalendars(true);   // при редактировании прошлые даты разрешены
  fpCheckin.setDate(b.check_in, false);
  if (b.check_in) {
    const m = new Date(b.check_in + 'T00:00:00');
    m.setDate(m.getDate() + 2);
    fpCheckout.set('minDate', m);
  }
  fpCheckout.setDate(b.check_out, false);
  calcTotal();
  openModal('modal-booking');
}

function calcTotal() {
  const ci            = document.getElementById('booking-checkin').value;
  const co            = document.getElementById('booking-checkout').value;
  const discount      = parseFloat(document.getElementById('booking-discount').value) || 0;   // сомы
  const extraPerGuest = parseFloat(document.getElementById('booking-extra').value) || 0;       // сом за 1 доп. гостя/сутки
  const guests        = parseInt(document.getElementById('booking-guests').value) || 0;
  const cap           = MAX_GUESTS || 0;
  if (!ci || !co) return;
  const nights      = Math.round((new Date(co) - new Date(ci)) / 86400000);
  const block       = document.getElementById('total-block');
  if (nights <= 0)  { block.style.display = 'none'; return; }
  const extraGuests = Math.max(0, guests - cap);
  const extraNight  = extraPerGuest * extraGuests;              // сом/сутки за всех доп. гостей
  const extraTotal  = extraNight * nights;
  const earlyChk    = document.getElementById('booking-early-checkin').checked;
  const lateChk     = document.getElementById('booking-late-checkout').checked;
  const pricePerNight = _editPrice !== null ? _editPrice : PRICE_PER_DAY;
  const earlyLate   = Math.round(pricePerNight / 2) * ((earlyChk ? 1 : 0) + (lateChk ? 1 : 0));
  const totalBefore = nights * pricePerNight + extraTotal + earlyLate;  // сомы
  const totalSom    = Math.max(0, totalBefore - discount);      // сомы
  const totalUsd    = RATE ? Math.round(totalSom / RATE) : 0;   // $ по глобальному курсу
  document.getElementById('total-usd').textContent    = `${totalSom.toLocaleString('ru-RU')} сом`;
  document.getElementById('total-tenge').textContent  = RATE ? `≈ $${totalUsd.toLocaleString('ru-RU')}` : '';
  document.getElementById('total-nights').textContent = `${nights} ночей`;
  const discLine = document.getElementById('total-discount-line');
  if (discount > 0) {
    discLine.textContent = `Скидка -${discount.toLocaleString('ru-RU')} сом · было ${totalBefore.toLocaleString('ru-RU')} сом`;
    discLine.style.display = 'block';
  } else {
    discLine.style.display = 'none';
  }
  const extraLine = document.getElementById('total-extra-line');
  if (extraTotal > 0) {
    extraLine.textContent = `Доп. гости: ${extraGuests} × ${extraPerGuest.toLocaleString('ru-RU')} сом × ${nights} ноч. = ${extraTotal.toLocaleString('ru-RU')} сом`;
    extraLine.style.display = 'block';
  } else {
    extraLine.style.display = 'none';
  }
  const elLine = document.getElementById('total-earlylate-line');
  if (earlyLate > 0) {
    const parts = [];
    if (earlyChk) parts.push('ранний заезд');
    if (lateChk)  parts.push('поздний выезд');
    elLine.textContent = `${parts.join(' + ')}: +${earlyLate.toLocaleString('ru-RU')} сом`;
    elLine.style.display = 'block';
  } else {
    elLine.style.display = 'none';
  }
  block.style.display = 'flex';
}

async function submitBookingPage(e) {
  e.preventDefault();
  const ci = document.getElementById('booking-checkin').value;
  const co = document.getElementById('booking-checkout').value;
  if (!ci || !co) { showToast('Выберите даты заезда и выезда', 'error'); return; }
  if (Math.round((new Date(co) - new Date(ci)) / 86400000) < 2) { showToast('Минимальный срок брони — 2 ночи', 'error'); return; }
  // При позднем выезде новая бронь занимает и день выезда
  const coChk = document.getElementById('booking-late-checkout').checked
    ? isoDate(new Date(new Date(co + 'T00:00:00').getTime() + 86400000)) : co;
  if (rangeOverlaps(ci, coChk)) { showToast('❌ Эти даты уже заняты!', 'error'); return; }
  const guestsN = parseInt(document.getElementById('booking-guests').value) || 0;
  const extraN  = parseFloat(document.getElementById('booking-extra').value) || 0;
  if (MAX_GUESTS && guestsN > MAX_GUESTS && extraN <= 0) { showToast(`Максимум гостей: ${MAX_GUESTS}. Укажите доплату за доп. гостя`, 'error'); return; }
  const id = document.getElementById('booking-id').value;
  const body = {
    cottage_id: COTTAGE_ID,
    guest_name: document.getElementById('booking-guest-name').value.trim(),
    check_in:   ci,
    check_out:  co,
    guests:     document.getElementById('booking-guests').value,
    discount:        parseFloat(document.getElementById('booking-discount').value) || 0,
    deposit_paid:    parseFloat(document.getElementById('booking-deposit').value) || 0,
    extra_per_guest: parseFloat(document.getElementById('booking-extra').value) || 0,
    early_checkin:        document.getElementById('booking-early-checkin').checked,
    late_checkout:        document.getElementById('booking-late-checkout').checked,
    payment_type:         document.getElementById('booking-payment').value,
    deposit_date:         document.getElementById('booking-deposit-date').value || null,
    deposit_payment_type: document.getElementById('booking-deposit-type').value,
    balance_date:         document.getElementById('booking-balance-date').value || null,
    notes:                document.getElementById('booking-notes').value.trim(),
  };
  const url    = id ? `/bookings/${id}` : '/bookings';
  const method = id ? 'PUT' : 'POST';
  const res  = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) { showToast(data.error, 'error'); return; }
  if (id) {
    // Редактирование — просто закрыть и перезагрузить
    showToast('Бронь обновлена!', 'success');
    closeModal('modal-booking');
    setTimeout(() => location.reload(), 700);
  } else {
    // Новая бронь — показать панель успеха с кнопкой «Ещё объект»
    _lastBookingBody = body;
    showBookingSuccessPanel(body.guest_name, body.check_in, body.check_out);
  }
}

async function deleteBooking(id) {
  if (!confirm('Удалить бронь?')) return;
  await fetch(`/bookings/${id}`, { method: 'DELETE' });
  document.getElementById(`row-${id}`)?.remove();
  showToast('Бронь удалена');
}
