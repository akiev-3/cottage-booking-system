from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
import json
import os
import io
import csv
from datetime import datetime, date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

app = Flask(__name__)

# Абсолютный путь — данные всегда найдутся независимо от того,
# из какой папки запускается приложение
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "data.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"cottages": [], "bookings": [], "settings": {"rate": 500}}
    data = json.load(open(DATA_FILE, encoding="utf-8"))
    data.setdefault("settings", {"rate": 500})
    # Совместимость со старыми бронями без поля rate/total_som
    for b in data.get("bookings", []):
        if "rate" not in b:
            b["rate"] = data["settings"]["rate"]
        if "total_som" not in b:
            b["total_som"] = round(b["total"] * b["rate"])
    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fmt_date(iso: str) -> str:
    """YYYY-MM-DD → ДД/ММ/ГГГГ"""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso


def next_id(items):
    return max((i["id"] for i in items), default=0) + 1


app.jinja_env.filters["fmtdate"] = fmt_date


@app.route("/")
def index():
    data = load_data()
    return render_template("index.html", cottages=data["cottages"], rate=data["settings"]["rate"])


# ── Settings ──────────────────────────────────────────────

@app.route("/settings", methods=["GET"])
def get_settings():
    data = load_data()
    return jsonify(data["settings"])


@app.route("/settings", methods=["POST"])
def update_settings():
    data = load_data()
    body = request.json
    if "rate" in body:
        data["settings"]["rate"] = float(body["rate"])
    save_data(data)
    return jsonify(data["settings"])


# ── Cottages ──────────────────────────────────────────────

@app.route("/cottages", methods=["POST"])
def create_cottage():
    data = load_data()
    body = request.json
    cottage = {
        "id": next_id(data["cottages"]),
        "name": body["name"],
        "capacity": int(body["capacity"]),
        "price_per_day": float(body["price_per_day"]),
        "description": body.get("description", ""),
    }
    data["cottages"].append(cottage)
    save_data(data)
    return jsonify(cottage), 201


@app.route("/cottages/<int:cottage_id>", methods=["PUT"])
def update_cottage(cottage_id):
    data = load_data()
    body = request.json
    for c in data["cottages"]:
        if c["id"] == cottage_id:
            c["name"]          = body.get("name", c["name"])
            c["capacity"]      = int(body.get("capacity", c["capacity"]))
            c["price_per_day"] = float(body.get("price_per_day", c["price_per_day"]))
            c["description"]   = body.get("description", c.get("description", ""))
            save_data(data)
            return jsonify(c)
    return jsonify({"error": "Не найдено"}), 404


@app.route("/cottages/<int:cottage_id>", methods=["DELETE"])
def delete_cottage(cottage_id):
    data = load_data()
    data["cottages"] = [c for c in data["cottages"] if c["id"] != cottage_id]
    data["bookings"] = [b for b in data["bookings"] if b["cottage_id"] != cottage_id]
    save_data(data)
    return jsonify({"ok": True})


# ── Bookings ──────────────────────────────────────────────

@app.route("/bookings", methods=["GET"])
def get_bookings():
    data = load_data()
    cottage_id = request.args.get("cottage_id", type=int)
    bookings = data["bookings"]
    if cottage_id:
        bookings = [b for b in bookings if b["cottage_id"] == cottage_id]
    return jsonify(bookings)


@app.route("/bookings", methods=["POST"])
def create_booking():
    data   = load_data()
    body   = request.json
    cottage_id = int(body["cottage_id"])
    check_in   = body["check_in"]
    check_out  = body["check_out"]
    guests     = int(body["guests"])

    cottage = next((c for c in data["cottages"] if c["id"] == cottage_id), None)
    if not cottage:
        return jsonify({"error": "Коттедж не найден"}), 404

    if guests > cottage["capacity"]:
        return jsonify({"error": f"Максимум гостей: {cottage['capacity']}"}), 400

    ci = datetime.strptime(check_in,  "%Y-%m-%d").date()
    co = datetime.strptime(check_out, "%Y-%m-%d").date()
    if co <= ci:
        return jsonify({"error": "Дата выезда должна быть позже даты заезда"}), 400

    for b in data["bookings"]:
        if b["cottage_id"] != cottage_id:
            continue
        bi = datetime.strptime(b["check_in"],  "%Y-%m-%d").date()
        bo = datetime.strptime(b["check_out"], "%Y-%m-%d").date()
        if ci < bo and co > bi:
            return jsonify({"error": f"Даты пересекаются с бронью #{b['id']} ({b['check_in']} – {b['check_out']})"}), 409

    nights = (co - ci).days
    total  = nights * cottage["price_per_day"]

    # Берём курс из формы; если не передан — из настроек
    rate = float(body.get("rate") or data["settings"]["rate"])

    booking = {
        "id":           next_id(data["bookings"]),
        "cottage_id":   cottage_id,
        "cottage_name": cottage["name"],
        "guest_name":   body.get("guest_name", ""),
        "guests":       guests,
        "check_in":     check_in,
        "check_out":    check_out,
        "nights":       nights,
        "total":        total,          # в долларах
        "rate":         rate,           # курс на момент бронирования
        "total_som":    total * rate,   # сумма в сомах
        "notes":        body.get("notes", ""),
    }
    data["bookings"].append(booking)
    save_data(data)
    return jsonify(booking), 201


@app.route("/bookings/<int:booking_id>", methods=["DELETE"])
def delete_booking(booking_id):
    data = load_data()
    data["bookings"] = [b for b in data["bookings"] if b["id"] != booking_id]
    save_data(data)
    return jsonify({"ok": True})


@app.route("/cottages/<int:cottage_id>/bookings")
def cottage_bookings_page(cottage_id):
    data    = load_data()
    cottage = next((c for c in data["cottages"] if c["id"] == cottage_id), None)
    if not cottage:
        return redirect(url_for("index"))
    bookings = sorted(
        [b for b in data["bookings"] if b["cottage_id"] == cottage_id],
        key=lambda b: b["check_in"]
    )
    today = date.today().isoformat()
    rate  = data["settings"]["rate"]
    return render_template("cottage.html", cottage=cottage, bookings=bookings, today=today, rate=rate)


# ── Excel export ──────────────────────────────────────────

def _header_fill(color):
    return PatternFill("solid", fgColor=color)

def _thin_border():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

# Колонки и ширины — единое место, используется везде
BOOK_HEADERS = [
    "№", "Коттедж", "Гость", "Заезд", "Выезд",
    "Ночей", "Гостей", "Сумма ($)", "Сумма (сом)", "Курс", "Заметки"
]
BOOK_WIDTHS = [6, 22, 22, 13, 13, 8, 8, 13, 14, 8, 30]
# Индексы (1-based) для выравнивания по центру
CENTER_COLS = {1, 6, 7, 8, 9, 10}


def _booking_row(b, current_rate):
    """Вернуть список значений строки брони."""
    b_rate    = b.get("rate", current_rate)          # курс на момент бронирования
    total_usd = b["total"]                            # всегда в $
    total_som = b.get("total_som", total_usd * b_rate)
    return [
        b["id"],
        b["cottage_name"],
        b["guest_name"],
        fmt_date(b["check_in"]),
        fmt_date(b["check_out"]),
        b["nights"],
        b["guests"],
        total_usd,
        round(total_som),
        b_rate,
        b.get("notes", ""),
    ]


def _write_headers(ws, headers, widths, row=1):
    hf = Font(bold=True, color="FFFFFF")
    hfill = _header_fill("4F6EF7")
    center = Alignment(horizontal="center", vertical="center")
    border = _thin_border()
    for col, (h, w) in enumerate(zip(headers, widths), 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font      = hf
        cell.fill      = hfill
        cell.alignment = center
        cell.border    = border
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[row].height = 22


def _write_booking_rows(ws, bookings, current_rate, start_row=2):
    today  = date.today().isoformat()
    border = _thin_border()
    for row_i, b in enumerate(bookings, start_row):
        is_past  = b["check_out"] < today
        row_fill = PatternFill("solid", fgColor="F4F6F9") if is_past else PatternFill("solid", fgColor="FFFFFF")
        for col, val in enumerate(_booking_row(b, current_rate), 1):
            cell = ws.cell(row=row_i, column=col, value=val)
            cell.fill   = row_fill
            cell.border = border
            if col in CENTER_COLS:
                cell.alignment = Alignment(horizontal="center")
    return row_i if bookings else start_row - 1


def _write_totals(ws, bookings, current_rate, total_row):
    """Строка ИТОГО: суммы по $ и сом."""
    border = _thin_border()
    bold   = Font(bold=True)
    fill   = PatternFill("solid", fgColor="EEF2FF")
    labels = {1: "ИТОГО", 6: sum(b["nights"] for b in bookings)}

    total_usd = sum(b["total"] for b in bookings)
    total_som = sum(b.get("total_som", b["total"] * b.get("rate", current_rate)) for b in bookings)

    labels[8]  = round(total_usd)
    labels[9]  = round(total_som)

    for col in range(1, len(BOOK_HEADERS) + 1):
        cell = ws.cell(row=total_row, column=col, value=labels.get(col, None))
        cell.font   = bold
        cell.fill   = fill
        cell.border = border
        if col in CENTER_COLS:
            cell.alignment = Alignment(horizontal="center")


@app.route("/export/excel")
def export_excel():
    """Все брони всех коттеджей."""
    data         = load_data()
    current_rate = data["settings"]["rate"]
    wb           = Workbook()

    # ── Лист 1: Все брони ─────────────────────────────────
    ws_all = wb.active
    ws_all.title = "Все брони"
    _write_headers(ws_all, BOOK_HEADERS, BOOK_WIDTHS, row=1)

    bookings_sorted = sorted(data["bookings"], key=lambda b: b["check_in"])
    last = _write_booking_rows(ws_all, bookings_sorted, current_rate, start_row=2)
    if bookings_sorted:
        _write_totals(ws_all, bookings_sorted, current_rate, last + 1)

    ws_all.freeze_panes = "A2"
    ws_all.auto_filter.ref = f"A1:K{last}"

    # ── Лист 2: Сводка по коттеджам ───────────────────────
    ws_sum = wb.create_sheet("Сводка по коттеджам")
    sum_headers = ["Коттедж", "Вместимость", "Цена/сутки ($)", "Броней", "Ночей всего", "Выручка ($)", "Выручка (сом)"]
    sum_widths  = [24, 14, 16, 10, 14, 16, 18]
    _write_headers(ws_sum, sum_headers, sum_widths, row=1)

    border = _thin_border()
    for row_i, c in enumerate(data["cottages"], 2):
        cb = [b for b in data["bookings"] if b["cottage_id"] == c["id"]]
        rev_usd = sum(b["total"] for b in cb)
        rev_som = sum(b.get("total_som", b["total"] * b.get("rate", current_rate)) for b in cb)
        values  = [c["name"], c["capacity"], c["price_per_day"], len(cb),
                   sum(b["nights"] for b in cb), round(rev_usd), round(rev_som)]
        for col, val in enumerate(values, 1):
            cell = ws_sum.cell(row=row_i, column=col, value=val)
            cell.border = border
            if col > 1:
                cell.alignment = Alignment(horizontal="center")

    # ── Листы для каждого коттеджа ────────────────────────
    for c in data["cottages"]:
        ws = wb.create_sheet(c["name"][:28])

        # Шапка
        ws.merge_cells(f"A1:K1")
        tc = ws["A1"]
        tc.value     = f"{c['name']}  |  до {c['capacity']} чел.  |  ${int(c['price_per_day'])}/сутки  |  Курс: {current_rate} сом"
        tc.font      = Font(bold=True, size=12, color="2C3E50")
        tc.fill      = PatternFill("solid", fgColor="EEF2FF")
        tc.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 26

        _write_headers(ws, BOOK_HEADERS, BOOK_WIDTHS, row=2)

        cb = sorted([b for b in data["bookings"] if b["cottage_id"] == c["id"]],
                    key=lambda b: b["check_in"])
        last = _write_booking_rows(ws, cb, current_rate, start_row=3)
        if cb:
            _write_totals(ws, cb, current_rate, last + 1)

        ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"broni_{date.today().isoformat()}.xlsx")


@app.route("/export/excel/<int:cottage_id>")
def export_excel_cottage(cottage_id):
    """Брони одного коттеджа."""
    data         = load_data()
    current_rate = data["settings"]["rate"]
    cottage      = next((c for c in data["cottages"] if c["id"] == cottage_id), None)
    if not cottage:
        return jsonify({"error": "Не найдено"}), 404

    wb = Workbook()
    ws = wb.active
    ws.title = cottage["name"][:31]

    ws.merge_cells("A1:K1")
    tc = ws["A1"]
    tc.value     = f"{cottage['name']}  |  до {cottage['capacity']} чел.  |  ${int(cottage['price_per_day'])}/сутки  |  Курс: {current_rate} сом"
    tc.font      = Font(bold=True, size=12)
    tc.fill      = PatternFill("solid", fgColor="EEF2FF")
    tc.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 26

    _write_headers(ws, BOOK_HEADERS, BOOK_WIDTHS, row=2)

    cb = sorted([b for b in data["bookings"] if b["cottage_id"] == cottage_id],
                key=lambda b: b["check_in"])
    last = _write_booking_rows(ws, cb, current_rate, start_row=3)
    if cb:
        _write_totals(ws, cb, current_rate, last + 1)

    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{cottage['name']}_{date.today().isoformat()}.xlsx")


# ── CSV export ────────────────────────────────────────────

CSV_HEADERS = ["№", "Коттедж", "Гость", "Заезд", "Выезд",
               "Ночей", "Гостей", "Сумма ($)", "Курс", "Сумма (сом)", "Заметки"]

def _bookings_to_csv(bookings, current_rate) -> io.StringIO:
    buf = io.StringIO()
    buf.write("﻿")   # BOM — чтобы Excel открывал кириллицу корректно
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(CSV_HEADERS)
    for b in bookings:
        b_rate    = b.get("rate", current_rate)
        total_som = b.get("total_som", round(b["total"] * b_rate))
        writer.writerow([
            b["id"],
            b["cottage_name"],
            b["guest_name"],
            fmt_date(b["check_in"]),
            fmt_date(b["check_out"]),
            b["nights"],
            b["guests"],
            b["total"],
            b_rate,
            round(total_som),
            b.get("notes", ""),
        ])
    # Итого
    writer.writerow([])
    writer.writerow([
        "ИТОГО", "", "", "", "",
        sum(b["nights"] for b in bookings),
        "",
        round(sum(b["total"] for b in bookings)),
        "",
        round(sum(b.get("total_som", b["total"] * b.get("rate", current_rate)) for b in bookings)),
        "",
    ])
    buf.seek(0)
    return buf


@app.route("/export/csv")
def export_csv():
    """Все брони — CSV."""
    data         = load_data()
    current_rate = data["settings"]["rate"]
    bookings     = sorted(data["bookings"], key=lambda b: b["check_in"])
    buf = _bookings_to_csv(bookings, current_rate)
    return send_file(
        io.BytesIO(buf.read().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"broni_{date.today().isoformat()}.csv",
    )


@app.route("/export/csv/<int:cottage_id>")
def export_csv_cottage(cottage_id):
    """Брони одного коттеджа — CSV."""
    data         = load_data()
    current_rate = data["settings"]["rate"]
    cottage      = next((c for c in data["cottages"] if c["id"] == cottage_id), None)
    if not cottage:
        return jsonify({"error": "Не найдено"}), 404
    bookings = sorted(
        [b for b in data["bookings"] if b["cottage_id"] == cottage_id],
        key=lambda b: b["check_in"]
    )
    buf = _bookings_to_csv(bookings, current_rate)
    return send_file(
        io.BytesIO(buf.read().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{cottage['name']}_{date.today().isoformat()}.csv",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
