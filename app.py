from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import os
import io
import csv
import json
from datetime import datetime, date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cottage-secret-2024-change-me")

# ── Учётные данные ────────────────────────────────────────
LOGIN    = "admin"
PASSWORD = generate_password_hash(os.environ.get("APP_PASSWORD", "1234"))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


# ── База данных ───────────────────────────────────────────

def get_db():
    conn = psycopg2.connect(
        os.environ.get("DATABASE_URL", ""),
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn


def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cottages (
            id            SERIAL PRIMARY KEY,
            name          VARCHAR(255) NOT NULL,
            capacity      INT          DEFAULT 0,
            price_per_day FLOAT        DEFAULT 0,
            description   TEXT         DEFAULT '',
            contacts      TEXT         DEFAULT '',
            owner_type    VARCHAR(50)  DEFAULT 'Компания',
            property_type VARCHAR(50)  DEFAULT 'Коттедж',
            owner_name    VARCHAR(255) DEFAULT ''
        )
    """)
    # Миграции колонок
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS owner_type    VARCHAR(50)  DEFAULT 'Компания'")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS property_type VARCHAR(50)  DEFAULT 'Коттедж'")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS owner_name    VARCHAR(255) DEFAULT ''")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS contacts      TEXT         DEFAULT ''")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS capacity      INT          DEFAULT 0")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS price_per_day FLOAT        DEFAULT 0")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS cottage_size  VARCHAR(20)  DEFAULT ''")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS rooms         INT          DEFAULT 0")
    cur.execute("ALTER TABLE cottages ADD COLUMN IF NOT EXISTS floor         VARCHAR(20)  DEFAULT ''")
    # Миграция данных: старые owner_type → новые owner_type + property_type
    cur.execute("UPDATE cottages SET owner_type='Компания',  property_type='Коттедж'     WHERE owner_type IN ('Алма-Ата','Коттеджи')")
    cur.execute("UPDATE cottages SET owner_type='Компания',  property_type='Номер отеля' WHERE owner_type = 'Номера отеля'")
    cur.execute("UPDATE cottages SET owner_type='Собственник'                            WHERE owner_type = 'Собственник' AND property_type IS NULL")
    cur.execute("UPDATE cottages SET property_type='Коттедж' WHERE property_type IS NULL OR property_type = ''")
    # Для собственников: перенести description → contacts (если contacts пусто)
    cur.execute("""
        UPDATE cottages
        SET contacts = description, description = ''
        WHERE owner_type = 'Собственник' AND (contacts IS NULL OR contacts = '') AND description != ''
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id                   SERIAL PRIMARY KEY,
            cottage_id           INT REFERENCES cottages(id) ON DELETE CASCADE,
            cottage_name         VARCHAR(255),
            guest_name           VARCHAR(255),
            guests               INT,
            check_in             DATE,
            check_out            DATE,
            nights               INT,
            discount             FLOAT   DEFAULT 0,
            total_before_discount FLOAT,
            total                FLOAT,
            rate                 FLOAT,
            total_som            FLOAT,
            notes                TEXT    DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   VARCHAR(50) PRIMARY KEY,
            value VARCHAR(255)
        )
    """)
    cur.execute("""
        INSERT INTO settings (key, value)
        VALUES ('rate', '500')
        ON CONFLICT (key) DO NOTHING
    """)

    # ── Прайс-лист услуг ──────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_catalog (
            id         SERIAL PRIMARY KEY,
            category   VARCHAR(50)  NOT NULL,
            name       VARCHAR(255) NOT NULL,
            unit       VARCHAR(30)  DEFAULT 'шт',
            price      FLOAT        NOT NULL,
            has_plate  BOOLEAN      DEFAULT FALSE,
            owner_type VARCHAR(50)  DEFAULT 'Алма-Ата'
        )
    """)
    # Миграция: owner_type → канонические типы объектов
    cur.execute("ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS owner_type VARCHAR(50) DEFAULT 'Коттедж'")
    cur.execute("UPDATE service_catalog SET owner_type = 'Коттедж'     WHERE owner_type IN ('Алма-Ата','Коттеджи')")
    cur.execute("UPDATE service_catalog SET owner_type = 'Номер отеля' WHERE owner_type = 'Номера отеля'")
    # Заполняем дефолтный прайс-лист (только если пустой)
    cur.execute("SELECT COUNT(*) as cnt FROM service_catalog")
    if cur.fetchone()["cnt"] == 0:
        defaults = [
            ("cleaning",    "Уборка — малый коттедж",          "шт",    6000, False),
            ("cleaning",    "Уборка — большой коттедж",        "шт",    8000, False),
            ("cleaning",    "Мытьё окон",                      "шт",    5000, False),
            ("cleaning",    "Уборка после ремонта",            "м²",     100, False),
            ("parking",     "Парковка (собственник)",          "сутки",   50, True),
            ("parking",     "Парковка (гость/арендатор)",      "сутки",  100, True),
            ("specialist",  "Вызов сантехника",                "шт",    2000, False),
            ("specialist",  "Вызов электрика",                 "шт",    2000, False),
            ("laundry",     "Простынь двуспальная Х/Б",        "шт",     400, False),
            ("laundry",     "Простынь малая Х/Б",              "шт",     250, False),
            ("laundry",     "Простынь махровая",               "шт",     500, False),
            ("laundry",     "Пододеяльник односпальный Х/Б",   "шт",     400, False),
            ("laundry",     "Наволочка Х/Б",                   "шт",     100, False),
            ("laundry",     "Полотенце большое",               "шт",     400, False),
            ("laundry",     "Полотенце среднее",               "шт",     300, False),
            ("laundry",     "Полотенце маленькое",             "шт",     200, False),
            ("laundry",     "Салфетка столовая",               "шт",     100, False),
            ("laundry",     "Халат махровый",                  "шт",     500, False),
            ("laundry",     "Халат Х/Б",                       "шт",     400, False),
            ("laundry",     "Домашний текстиль (шторы, тюль)", "кг",     800, False),
        ]
        cur.executemany(
            "INSERT INTO service_catalog (category, name, unit, price, has_plate) VALUES (%s,%s,%s,%s,%s)",
            defaults
        )

    # ── Журнал заказов услуг ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_orders (
            id           SERIAL PRIMARY KEY,
            service_id   INT REFERENCES service_catalog(id) ON DELETE SET NULL,
            service_name VARCHAR(255),
            category     VARCHAR(50),
            cottage_id   INT REFERENCES cottages(id) ON DELETE SET NULL,
            cottage_name VARCHAR(255) DEFAULT '',
            service_date DATE        NOT NULL,
            end_date     DATE        DEFAULT NULL,
            quantity     FLOAT       DEFAULT 1,
            price        FLOAT       NOT NULL,
            total        FLOAT       NOT NULL,
            plate        VARCHAR(30) DEFAULT '',
            notes        TEXT        DEFAULT '',
            created_at   TIMESTAMP   DEFAULT NOW()
        )
    """)
    # Миграция: end_date + object_type (тип объекта на момент заказа)
    cur.execute("ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS end_date DATE DEFAULT NULL")
    cur.execute("ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS object_type VARCHAR(50) DEFAULT ''")
    # Бэкфилл object_type из связанного объекта
    cur.execute("""
        UPDATE service_orders so SET object_type = CASE
            WHEN c.owner_type = 'Собственник' THEN 'Собственник'
            ELSE c.property_type
        END
        FROM cottages c
        WHERE so.cottage_id = c.id AND (so.object_type IS NULL OR so.object_type = '')
    """)

    conn.commit()
    cur.close()
    conn.close()


def fmt_date(iso) -> str:
    """YYYY-MM-DD или date → ДД/ММ/ГГГГ"""
    try:
        if isinstance(iso, date):
            return iso.strftime("%d/%m/%Y")
        return datetime.strptime(str(iso), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(iso)


def serialize_booking(row) -> dict:
    """Конвертирует date-объекты PostgreSQL в строки ISO."""
    b = dict(row)
    for field in ("check_in", "check_out"):
        if isinstance(b.get(field), date):
            b[field] = b[field].isoformat()
    return b


def get_rate(cur) -> float:
    cur.execute("SELECT value FROM settings WHERE key = 'rate'")
    row = cur.fetchone()
    return float(row["value"]) if row else 500.0


app.jinja_env.filters["fmtdate"] = fmt_date


# ── Auth ──────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if (request.form.get("username") == LOGIN and
                check_password_hash(PASSWORD, request.form.get("password", ""))):
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Неверный логин или пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Main ──────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM cottages ORDER BY id")
    cottages = [dict(r) for r in cur.fetchall()]
    # Счётчик броней по каждому объекту
    cur.execute("SELECT cottage_id, COUNT(*) AS cnt FROM bookings GROUP BY cottage_id")
    counts = {r["cottage_id"]: r["cnt"] for r in cur.fetchall()}
    for c in cottages:
        c["bookings_count"] = counts.get(c["id"], 0)
    rate = get_rate(cur)
    cur.close(); conn.close()
    return render_template("index.html", cottages=cottages, rate=rate)


# ── Settings ──────────────────────────────────────────────

@app.route("/settings", methods=["GET"])
@login_required
def get_settings():
    conn = get_db(); cur = conn.cursor()
    rate = get_rate(cur)
    cur.close(); conn.close()
    return jsonify({"rate": rate})


@app.route("/settings", methods=["POST"])
@login_required
def update_settings():
    body = request.json
    conn = get_db(); cur = conn.cursor()
    if "rate" in body:
        cur.execute("UPDATE settings SET value = %s WHERE key = 'rate'", (str(body["rate"]),))
        conn.commit()
    rate = get_rate(cur)
    cur.close(); conn.close()
    return jsonify({"rate": rate})


# ── Cottages ──────────────────────────────────────────────

@app.route("/cottages", methods=["POST"])
@login_required
def create_cottage():
    body = request.json
    conn = get_db(); cur = conn.cursor()
    owner_type    = body.get("owner_type", "Компания")
    property_type = body.get("property_type", "Коттедж")
    cur.execute("""
        INSERT INTO cottages (name, capacity, price_per_day, description, contacts,
                              owner_type, property_type, owner_name, cottage_size, rooms, floor)
        VALUES (%s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s) RETURNING *
    """, (body["name"],
          int(body.get("capacity") or 0),
          float(body.get("price_per_day") or 0),
          body.get("description",""),
          body.get("contacts",""),
          owner_type, property_type,
          body.get("owner_name",""),
          body.get("cottage_size",""),
          int(body.get("rooms") or 0),
          body.get("floor","")))
    cottage = dict(cur.fetchone())
    conn.commit(); cur.close(); conn.close()
    return jsonify(cottage), 201


@app.route("/cottages/<int:cottage_id>", methods=["PUT"])
@login_required
def update_cottage(cottage_id):
    body = request.json
    conn = get_db(); cur = conn.cursor()
    owner_type    = body.get("owner_type", "Компания")
    property_type = body.get("property_type", "Коттедж")
    cur.execute("""
        UPDATE cottages SET name=%s, capacity=%s, price_per_day=%s,
                            description=%s, contacts=%s, owner_type=%s, property_type=%s, owner_name=%s,
                            cottage_size=%s, rooms=%s, floor=%s
        WHERE id=%s RETURNING *
    """, (body["name"],
          int(body.get("capacity") or 0),
          float(body.get("price_per_day") or 0),
          body.get("description",""),
          body.get("contacts",""),
          owner_type, property_type,
          body.get("owner_name",""),
          body.get("cottage_size",""),
          int(body.get("rooms") or 0),
          body.get("floor",""),
          cottage_id))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    if not row:
        return jsonify({"error": "Не найдено"}), 404
    return jsonify(dict(row))


@app.route("/cottages/<int:cottage_id>", methods=["DELETE"])
@login_required
def delete_cottage(cottage_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM cottages WHERE id = %s", (cottage_id,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


# ── Демо-данные ───────────────────────────────────────────

@app.route("/seed-demo", methods=["GET", "POST"])
@login_required
def seed_demo():
    """Генерирует тестовые брони и заказы услуг для объектов компании."""
    from datetime import timedelta
    import random, traceback

    conn = get_db(); cur = conn.cursor()
    try:
        return _do_seed(cur, conn, timedelta, random)
    except Exception as e:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()[-1500:]}), 500


def _do_seed(cur, conn, timedelta, random):
    # ── Демо-услуги для каждого типа объекта (если их нет) ──
    DEMO_SERVICES = {
        "Коттедж": [
            ("Уборка", "Генеральная уборка коттеджа", "шт", 7000),
            ("Стирка", "Комплект постельного белья", "компл", 1200),
            ("Сервис", "Доставка дров", "связка", 800),
        ],
        "Номер отеля": [
            ("Уборка", "Уборка номера", "шт", 1500),
            ("Сервис", "Завтрак в номер", "шт", 900),
            ("Стирка", "Смена полотенец", "компл", 500),
        ],
        "Квартира": [
            ("Уборка", "Уборка квартиры", "шт", 3000),
            ("Сервис", "Мытьё окон", "шт", 1500),
            ("Стирка", "Стирка штор", "кг", 700),
        ],
        "Номер для сотрудников": [
            ("Уборка", "Уборка комнаты", "шт", 1000),
            ("Стирка", "Смена белья", "компл", 600),
            ("Сервис", "Мелкий ремонт", "шт", 1500),
        ],
    }
    catalog_by_type = {}
    for otype, items in DEMO_SERVICES.items():
        cur.execute("SELECT id, name FROM service_catalog WHERE owner_type=%s", (otype,))
        existing = {r["name"] for r in cur.fetchall()}
        for cat, name, unit, price in items:
            if name not in existing:
                cur.execute("""
                    INSERT INTO service_catalog (category, name, unit, price, has_plate, owner_type)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (cat, name, unit, price, False, otype))
        cur.execute("SELECT * FROM service_catalog WHERE owner_type=%s", (otype,))
        catalog_by_type[otype] = [dict(r) for r in cur.fetchall()]

    # ── Объекты компании ──
    cur.execute("SELECT * FROM cottages WHERE owner_type='Компания' ORDER BY id")
    objects = [dict(r) for r in cur.fetchall()]

    rate = get_rate(cur)
    guests_names = ["Азамат", "Нурлан", "Айгерим", "Данияр", "Жанна",
                    "Тимур", "Алина", "Бекзат", "Мадина", "Ерлан"]
    nights_variants = [1, 2, 3, 5, 7]

    bookings_added = 0
    orders_added   = 0

    for obj in objects:
        # Чистим старые демо-брони этого объекта чтобы не плодить дубли? Нет — просто добавляем без пересечений.
        # Определяем стартовую дату: после последней существующей брони
        cur.execute("SELECT MAX(check_out) AS m FROM bookings WHERE cottage_id=%s", (obj["id"],))
        row = cur.fetchone()
        cursor_date = (row["m"] if row and row["m"] else date.today())
        if isinstance(cursor_date, str):
            cursor_date = datetime.strptime(cursor_date, "%Y-%m-%d").date()
        cursor_date = max(cursor_date, date.today()) + timedelta(days=2)

        price = obj.get("price_per_day") or 100
        for i in range(5):
            nights = nights_variants[i % len(nights_variants)]
            ci = cursor_date
            co = ci + timedelta(days=nights)
            total = round(nights * price)
            cur.execute("""
                INSERT INTO bookings (cottage_id, cottage_name, guest_name, guests,
                    check_in, check_out, nights, discount, total_before_discount,
                    total, rate, total_som, notes)
                VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s,%s,%s)
            """, (obj["id"], obj["name"], random.choice(guests_names),
                  max(1, (obj.get("capacity") or 2)), ci, co, nights,
                  0, total, total, rate, round(total*rate),
                  f"Демо-бронь #{i+1}"))
            bookings_added += 1
            cursor_date = co + timedelta(days=random.randint(1, 3))  # зазор между бронями

        # ── 5 заказов услуг для типа этого объекта ──
        otype = obj["property_type"]
        services = catalog_by_type.get(otype, [])
        if services:
            for j in range(5):
                svc = random.choice(services)
                qty = random.choice([1, 1, 2, 3])
                sp  = svc["price"]
                sdate = date.today() + timedelta(days=random.randint(0, 20))
                cur.execute("""
                    INSERT INTO service_orders (service_id, service_name, category,
                        cottage_id, cottage_name, service_date, end_date, quantity,
                        price, total, plate, notes, object_type)
                    VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s)
                """, (svc["id"], svc["name"], svc["category"], obj["id"], obj["name"],
                      sdate, None, qty, sp, round(qty*sp), "",
                      f"Демо-заказ #{j+1}", otype))
                orders_added += 1

    conn.commit(); cur.close(); conn.close()
    return jsonify({
        "ok": True,
        "objects": len(objects),
        "bookings_added": bookings_added,
        "orders_added": orders_added,
        "message": f"Создано {bookings_added} броней и {orders_added} заказов услуг для {len(objects)} объектов."
    })


# ── Bookings ──────────────────────────────────────────────

@app.route("/bookings", methods=["GET"])
@login_required
def get_bookings():
    cottage_id = request.args.get("cottage_id", type=int)
    conn = get_db(); cur = conn.cursor()
    if cottage_id:
        cur.execute("SELECT * FROM bookings WHERE cottage_id=%s ORDER BY check_in", (cottage_id,))
    else:
        cur.execute("SELECT * FROM bookings ORDER BY check_in")
    rows = [serialize_booking(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(rows)


@app.route("/bookings", methods=["POST"])
@login_required
def create_booking():
    body       = request.json
    cottage_id = int(body["cottage_id"])
    check_in   = body["check_in"]
    check_out  = body["check_out"]
    guests     = int(body["guests"])

    conn = get_db(); cur = conn.cursor()

    cur.execute("SELECT * FROM cottages WHERE id = %s", (cottage_id,))
    cottage = cur.fetchone()
    if not cottage:
        cur.close(); conn.close()
        return jsonify({"error": "Коттедж не найден"}), 404

    if guests > cottage["capacity"]:
        cur.close(); conn.close()
        return jsonify({"error": f"Максимум гостей: {cottage['capacity']}"}), 400

    ci = datetime.strptime(check_in,  "%Y-%m-%d").date()
    co = datetime.strptime(check_out, "%Y-%m-%d").date()
    if co <= ci:
        cur.close(); conn.close()
        return jsonify({"error": "Дата выезда должна быть позже даты заезда"}), 400

    # Проверка пересечений
    cur.execute("""
        SELECT id, check_in, check_out FROM bookings
        WHERE cottage_id = %s AND check_in < %s AND check_out > %s
    """, (cottage_id, co, ci))
    conflict = cur.fetchone()
    if conflict:
        cur.close(); conn.close()
        return jsonify({"error": f"Даты пересекаются с бронью #{conflict['id']} ({fmt_date(conflict['check_in'])} – {fmt_date(conflict['check_out'])})"}), 409

    nights        = (co - ci).days
    total_before  = nights * cottage["price_per_day"]
    discount      = max(0, float(body.get("discount") or 0))
    total         = round(max(0, total_before - discount), 2)
    rate          = float(body.get("rate") or get_rate(cur))
    total_som     = round(total * rate)

    cur.execute("""
        INSERT INTO bookings
            (cottage_id, cottage_name, guest_name, guests,
             check_in, check_out, nights,
             discount, total_before_discount, total, rate, total_som, notes)
        VALUES (%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s,%s,%s)
        RETURNING *
    """, (cottage_id, cottage["name"], body.get("guest_name", ""), guests,
          ci, co, nights,
          discount, total_before, total, rate, total_som, body.get("notes", "")))
    booking = dict(cur.fetchone())
    conn.commit(); cur.close(); conn.close()

    # Сериализуем даты
    booking["check_in"]  = str(booking["check_in"])
    booking["check_out"] = str(booking["check_out"])
    return jsonify(booking), 201


@app.route("/bookings/<int:booking_id>", methods=["DELETE"])
@login_required
def delete_booking(booking_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM bookings WHERE id = %s", (booking_id,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/cottages/<int:cottage_id>/booked-ranges")
@login_required
def cottage_booked_ranges(cottage_id):
    """Занятые диапазоны дат объекта — для подсветки в календаре."""
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT check_in, check_out FROM bookings WHERE cottage_id = %s ORDER BY check_in", (cottage_id,))
    ranges = [{"from": str(r["check_in"]), "to": str(r["check_out"])} for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify(ranges)


@app.route("/cottages/<int:cottage_id>/bookings")
@login_required
def cottage_bookings_page(cottage_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM cottages WHERE id = %s", (cottage_id,))
    cottage = cur.fetchone()
    if not cottage:
        cur.close(); conn.close()
        return redirect(url_for("index"))
    cur.execute("SELECT * FROM bookings WHERE cottage_id = %s ORDER BY check_in", (cottage_id,))
    bookings = [serialize_booking(r) for r in cur.fetchall()]
    rate  = get_rate(cur)
    today = date.today().isoformat()
    cur.close(); conn.close()
    # Занятые диапазоны для подсветки в календаре
    booked_ranges = [{"from": b["check_in"], "to": b["check_out"]} for b in bookings]
    return render_template("cottage.html", cottage=dict(cottage),
                           bookings=bookings, today=today, rate=rate,
                           booked_ranges=booked_ranges)


# ── Services ──────────────────────────────────────────────

CATEGORY_LABELS = {
    "cleaning":   "🧹 Уборка",
    "parking":    "🚗 Парковка",
    "laundry":    "👕 Стирка",
    "specialist": "🔧 Специалист",
}

# Канонические типы объектов: значение БД → (ключ, подпись)
OBJECT_TYPES = [
    ("Коттедж",               "cottage",   "🏠 Коттеджи"),
    ("Номер отеля",           "hotel",     "🏨 Номера отеля"),
    ("Квартира",              "apartment", "🏢 Квартиры"),
    ("Номер для сотрудников", "employee",  "👷 Сотрудники"),
    ("Собственник",           "private",   "👤 Собственники"),
]
OBJ_KEY = {name: key for name, key, _ in OBJECT_TYPES}      # 'Коттедж' → 'cottage'
OBJ_LABEL = {name: lbl for name, _, lbl in OBJECT_TYPES}

@app.route("/services")
@login_required
def services_page():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM service_catalog ORDER BY owner_type, category, id")
    catalog = [dict(r) for r in cur.fetchall()]

    # Группируем каталог по типу объекта → категории
    from collections import defaultdict
    grouped = defaultdict(lambda: defaultdict(list))
    for item in catalog:
        grouped[item["owner_type"]][item["category"]].append(item)
    # Каталоги по каждому типу
    catalogs = {key: dict(grouped.get(name, {})) for name, key, _ in OBJECT_TYPES}

    cur.execute("""
        SELECT so.*, c.name as cname, c.owner_type as c_owner, c.property_type as c_ptype
        FROM service_orders so
        LEFT JOIN cottages c ON c.id = so.cottage_id
        ORDER BY so.service_date DESC, so.id DESC
    """)
    orders = [dict(r) for r in cur.fetchall()]
    for o in orders:
        for f in ("service_date", "end_date"):
            if isinstance(o.get(f), date):
                o[f] = o[f].isoformat()
        # Тип объекта для фильтра: object_type или вычислить из объекта
        ot = o.get("object_type") or ""
        if not ot:
            if o.get("c_owner") == "Собственник":
                ot = "Собственник"
            elif o.get("c_ptype"):
                ot = o["c_ptype"]
        o["object_type"] = ot
        o["object_key"]  = OBJ_KEY.get(ot, "")
    cur.execute("SELECT * FROM cottages ORDER BY name")
    cottages = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return render_template("services.html",
        catalog=catalog, orders=orders,
        catalogs=catalogs, object_types=OBJECT_TYPES,
        cottages=cottages, categories=CATEGORY_LABELS,
        catalog_json=json.dumps(catalog))


@app.route("/service-catalog/<int:item_id>", methods=["PUT"])
@login_required
def update_catalog_item(item_id):
    body = request.json
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE service_catalog SET name=%s, price=%s, unit=%s, owner_type=%s
        WHERE id=%s RETURNING *
    """, (body["name"], float(body["price"]), body["unit"],
          body.get("owner_type","Алма-Ата"), item_id))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    if not row: return jsonify({"error": "Не найдено"}), 404
    return jsonify(dict(row))


@app.route("/service-catalog", methods=["POST"])
@login_required
def add_catalog_item():
    body = request.json
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO service_catalog (category, name, unit, price, has_plate, owner_type)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
    """, (body["category"], body["name"], body.get("unit","шт"),
          float(body["price"]), body.get("has_plate", False),
          body.get("owner_type","Коттедж")))
    row = dict(cur.fetchone())
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201


@app.route("/service-catalog/<int:item_id>", methods=["DELETE"])
@login_required
def delete_catalog_item(item_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM service_catalog WHERE id=%s", (item_id,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


@app.route("/service-orders", methods=["POST"])
@login_required
def create_service_order():
    body = request.json
    conn = get_db(); cur = conn.cursor()

    svc = None
    if body.get("service_id"):
        cur.execute("SELECT * FROM service_catalog WHERE id=%s", (int(body["service_id"]),))
        svc = cur.fetchone()

    # Если услуга не из прайса — создаём «виртуальный» объект из переданных данных
    if not svc:
        custom_name = body.get("custom_name","").strip()
        if not custom_name:
            cur.close(); conn.close()
            return jsonify({"error": "Введите название услуги"}), 400
        svc = {"id": None, "name": custom_name, "category": "cleaning",
               "unit": "шт", "price": float(body.get("price",0)), "has_plate": False}

    cottage_id   = body.get("cottage_id") or None
    cottage_name = ""
    object_type  = body.get("object_type", "")   # тип объекта из формы
    if cottage_id:
        cur.execute("SELECT name, owner_type, property_type FROM cottages WHERE id=%s", (int(cottage_id),))
        c = cur.fetchone()
        if c:
            cottage_name = c["name"]
            if not object_type:
                object_type = "Собственник" if c["owner_type"] == "Собственник" else c["property_type"]

    price    = float(body.get("price") or svc["price"])
    end_date = body.get("end_date") or None

    # Для парковки считаем дни между датами автоматически
    if end_date and svc["has_plate"]:
        from datetime import date as _date
        d1 = datetime.strptime(body["service_date"], "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()
        qty = max(1, (d2 - d1).days)
    else:
        qty = float(body.get("quantity") or 1)

    total = round(qty * price)

    # Используем кастомное название если введено вручную
    service_name = body.get("custom_name","").strip() or svc["name"]

    cur.execute("""
        INSERT INTO service_orders
            (service_id, service_name, category, cottage_id, cottage_name,
             service_date, end_date, quantity, price, total, plate, notes, object_type)
        VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
    """, (svc["id"], service_name, svc["category"],
          cottage_id, cottage_name,
          body["service_date"], end_date, qty, price, total,
          body.get("plate",""), body.get("notes",""), object_type))
    order = dict(cur.fetchone())
    conn.commit(); cur.close(); conn.close()
    for f in ("service_date", "end_date"):
        if isinstance(order.get(f), date):
            order[f] = order[f].isoformat()
    return jsonify(order), 201


@app.route("/service-orders/<int:order_id>", methods=["DELETE"])
@login_required
def delete_service_order(order_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM service_orders WHERE id=%s", (order_id,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})


def _build_services_excel(orders, sheet_title):
    """Строит Excel-файл по списку заказов услуг."""
    wb  = Workbook()
    ws  = wb.active
    ws.title = sheet_title[:31]

    headers    = ["№","Дата начала","Дата окончания","Категория","Услуга",
                  "Коттедж","Кол-во","Цена (сом)","Итого (сом)","Гос. номер","Заметки"]
    col_widths = [6, 14, 16, 18, 34, 22, 8, 13, 14, 16, 30]
    hf     = Font(bold=True, color="FFFFFF")
    hfill  = _header_fill("4F6EF7")
    border = _thin_border()
    center = Alignment(horizontal="center", vertical="center")
    CENTER = {1, 2, 3, 7, 8, 9}

    for col, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font=hf; cell.fill=hfill; cell.alignment=center; cell.border=border
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[1].height = 22

    for seq, (ri, o) in enumerate(zip(range(2, 2 + len(orders)), orders), 1):
        values = [
            seq,
            fmt_date(o["service_date"]) if o.get("service_date") else "",
            fmt_date(o["end_date"])     if o.get("end_date")     else "—",
            o.get("category",""),
            o.get("service_name",""),
            o.get("cottage_name","") or "—",
            o.get("quantity", 1),
            o.get("price", 0),
            o.get("total", 0),
            o.get("plate","") or "—",
            o.get("notes",""),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=ri, column=col, value=val)
            cell.fill = PatternFill("solid", fgColor="FFFFFF")
            cell.border = border
            if col in CENTER:
                cell.alignment = Alignment(horizontal="center")

    if orders:
        last = len(orders) + 2
        bold = Font(bold=True)
        fill = PatternFill("solid", fgColor="EEF2FF")
        for col in range(1, len(headers)+1):
            cell = ws.cell(row=last, column=col)
            cell.font=bold; cell.fill=fill; cell.border=border
        ws.cell(row=last, column=1, value="ИТОГО").font = bold
        total_cell = ws.cell(row=last, column=9, value=round(sum(o.get("total",0) for o in orders)))
        total_cell.font = bold
        total_cell.alignment = Alignment(horizontal="center")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:K{max(len(orders),1)+1}"
    return wb


def _fetch_service_orders(cur, object_type=None):
    """object_type — каноническое название типа ('Коттедж', 'Номер отеля', ...).
    Фильтрует по сохранённому object_type, а для старых записей — по типу связанного объекта."""
    if object_type:
        cur.execute("""
            SELECT so.*
            FROM service_orders so
            LEFT JOIN cottages c ON c.id = so.cottage_id
            WHERE COALESCE(NULLIF(so.object_type, ''),
                           CASE WHEN c.owner_type = 'Собственник' THEN 'Собственник'
                                ELSE c.property_type END) = %s
            ORDER BY so.service_date, so.id
        """, (object_type,))
    else:
        cur.execute("SELECT * FROM service_orders ORDER BY service_date, id")
    orders = [dict(r) for r in cur.fetchall()]
    for o in orders:
        for f in ("service_date", "end_date"):
            if isinstance(o.get(f), date):
                o[f] = o[f].isoformat()
    return orders


@app.route("/export/excel/services")
@login_required
def export_excel_services():
    conn = get_db(); cur = conn.cursor()
    orders = _fetch_service_orders(cur)
    cur.close(); conn.close()
    wb  = _build_services_excel(orders, "Все услуги")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"uslugi_vse_{date.today()}.xlsx")


@app.route("/export/excel/services/<obj_key>")
@login_required
def export_excel_services_by_type(obj_key):
    """Экспорт услуг по типу объекта: cottage / hotel / apartment / employee / private."""
    KEY_TO_NAME = {key: name for name, key, _ in OBJECT_TYPES}
    obj_name = KEY_TO_NAME.get(obj_key)
    if not obj_name:
        return redirect(url_for("export_excel_services"))
    conn = get_db(); cur = conn.cursor()
    orders = _fetch_service_orders(cur, object_type=obj_name)
    cur.close(); conn.close()
    wb  = _build_services_excel(orders, f"Услуги — {obj_name}")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"uslugi_{obj_key}_{date.today()}.xlsx")


# ── Excel helpers ─────────────────────────────────────────

BOOK_HEADERS = ["№","Коттедж","Гость","Заезд","Выезд",
                "Ночей","Гостей","Скидка ($)","Сумма ($)","Сумма (сом)","Курс","Заметки"]
BOOK_WIDTHS  = [6,22,22,13,13,8,8,11,13,14,8,30]
CENTER_COLS  = {1,6,7,8,9,10,11}

def _header_fill(color): return PatternFill("solid", fgColor=color)
def _thin_border():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

def _booking_row(b, seq_num):
    discount = b.get("discount") or 0
    return [
        seq_num, b["cottage_name"], b["guest_name"],
        fmt_date(b["check_in"]), fmt_date(b["check_out"]),
        b["nights"], b["guests"],
        f"-${discount}" if discount else "—",
        b["total"], round(b["total_som"] or 0), b["rate"],
        b.get("notes",""),
    ]

def _write_headers(ws, row=1):
    hf = Font(bold=True, color="FFFFFF")
    hfill = _header_fill("4F6EF7")
    border = _thin_border()
    center = Alignment(horizontal="center", vertical="center")
    for col,(h,w) in enumerate(zip(BOOK_HEADERS, BOOK_WIDTHS), 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font=hf; cell.fill=hfill; cell.alignment=center; cell.border=border
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[row].height = 22

def _write_rows(ws, bookings, start=2):
    today  = date.today().isoformat()
    border = _thin_border()
    last   = start - 1
    for seq, (row_i, b) in enumerate(zip(range(start, start + len(bookings)), bookings), 1):
        is_past  = str(b["check_out"]) < today
        row_fill = PatternFill("solid", fgColor="F4F6F9" if is_past else "FFFFFF")
        for col, val in enumerate(_booking_row(b, seq), 1):
            cell = ws.cell(row=row_i, column=col, value=val)
            cell.fill=row_fill; cell.border=border
            if col in CENTER_COLS:
                cell.alignment = Alignment(horizontal="center")
        last = row_i
    return last

def _write_totals(ws, bookings, total_row):
    border = _thin_border()
    bold   = Font(bold=True)
    fill   = PatternFill("solid", fgColor="EEF2FF")
    vals   = {1:"ИТОГО", 6:sum(b["nights"] for b in bookings),
              9:round(sum(b["total"] for b in bookings)),
              10:round(sum(b["total_som"] or 0 for b in bookings))}
    for col in range(1, len(BOOK_HEADERS)+1):
        cell = ws.cell(row=total_row, column=col, value=vals.get(col))
        cell.font=bold; cell.fill=fill; cell.border=border
        if col in CENTER_COLS:
            cell.alignment = Alignment(horizontal="center")


@app.route("/export/excel")
@login_required
def export_excel():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM cottages ORDER BY id")
    cottages = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM bookings ORDER BY check_in")
    all_bookings = [serialize_booking(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    wb = Workbook()

    # Лист: Все брони
    ws = wb.active; ws.title = "Все брони"
    _write_headers(ws, row=1)
    last = _write_rows(ws, all_bookings, start=2)
    if all_bookings: _write_totals(ws, all_bookings, last+1)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{last}"

    # Лист: Сводка — только коттеджи и номера компании (без частников)
    company_cottages = [c for c in cottages if c.get("owner_type") == "Компания"]
    ws2 = wb.create_sheet("Сводка")
    sh  = ["№","Объект","Тип","Вместимость","$/сутки","Броней","Ночей","Выручка ($)","Выручка (сом)"]
    sw  = [5,22,14,13,12,9,10,14,16]
    hf  = Font(bold=True,color="FFFFFF"); hfill=_header_fill("4F6EF7")
    border=_thin_border(); center=Alignment(horizontal="center",vertical="center")
    for col,(h,w) in enumerate(zip(sh,sw),1):
        cell=ws2.cell(row=1,column=col,value=h)
        cell.font=hf;cell.fill=hfill;cell.alignment=center;cell.border=border
        ws2.column_dimensions[cell.column_letter].width=w
    for seq,(ri,c) in enumerate(zip(range(2, 2+len(company_cottages)), company_cottages), 1):
        cb=[b for b in all_bookings if b["cottage_id"]==c["id"]]
        vals=[seq, c["name"], c.get("property_type","Коттедж"),
              c["capacity"], c["price_per_day"], len(cb),
              sum(b["nights"] for b in cb),
              round(sum(b["total"] for b in cb)),
              round(sum(b["total_som"] or 0 for b in cb))]
        for col,val in enumerate(vals,1):
            cell=ws2.cell(row=ri,column=col,value=val)
            cell.border=border
            if col>1: cell.alignment=Alignment(horizontal="center")

    # Листы по коттеджам
    for c in cottages:
        ws3 = wb.create_sheet(c["name"][:28])
        ws3.merge_cells("A1:L1")
        tc=ws3["A1"]
        tc.value=f"{c['name']}  |  до {c['capacity']} чел.  |  ${int(c['price_per_day'])}/сутки"
        tc.font=Font(bold=True,size=12,color="2C3E50")
        tc.fill=PatternFill("solid",fgColor="EEF2FF")
        tc.alignment=Alignment(horizontal="left",vertical="center")
        ws3.row_dimensions[1].height=26
        _write_headers(ws3, row=2)
        cb=[b for b in all_bookings if b["cottage_id"]==c["id"]]
        last=_write_rows(ws3, cb, start=3)
        if cb: _write_totals(ws3, cb, last+1)
        ws3.freeze_panes="A3"

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=f"broni_{date.today()}.xlsx")


@app.route("/export/excel/<int:cottage_id>")
@login_required
def export_excel_cottage(cottage_id):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM cottages WHERE id=%s",(cottage_id,))
    cottage=cur.fetchone()
    if not cottage: cur.close();conn.close(); return jsonify({"error":"Не найдено"}),404
    cur.execute("SELECT * FROM bookings WHERE cottage_id=%s ORDER BY check_in",(cottage_id,))
    bookings=[serialize_booking(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    wb=Workbook(); ws=wb.active; ws.title=cottage["name"][:31]
    ws.merge_cells("A1:L1"); tc=ws["A1"]
    tc.value=f"{cottage['name']}  |  до {cottage['capacity']} чел.  |  ${int(cottage['price_per_day'])}/сутки"
    tc.font=Font(bold=True,size=12); tc.fill=PatternFill("solid",fgColor="EEF2FF")
    tc.alignment=Alignment(horizontal="left",vertical="center"); ws.row_dimensions[1].height=26
    _write_headers(ws, row=2)
    last=_write_rows(ws, bookings, start=3)
    if bookings: _write_totals(ws, bookings, last+1)
    ws.freeze_panes="A3"

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=f"{cottage['name']}_{date.today()}.xlsx")


# ── CSV export ────────────────────────────────────────────

CSV_HEADERS = ["№","Коттедж/Номер","Гость","Заезд","Выезд",
               "Ночей","Гостей","Скидка ($)","Сумма ($)","Курс","Сумма (сом)","Заметки"]

def _to_csv(bookings):
    buf=io.StringIO()
    writer=csv.writer(buf, delimiter=";")
    writer.writerow(CSV_HEADERS)
    for seq, b in enumerate(bookings, 1):
        discount=b.get("discount") or 0
        writer.writerow([seq,b["cottage_name"],b["guest_name"],
            fmt_date(b["check_in"]),fmt_date(b["check_out"]),
            b["nights"],b["guests"],
            f"-${discount}" if discount else "—",
            b["total"],b["rate"],round(b["total_som"] or 0),b.get("notes","")])
    writer.writerow([])
    writer.writerow(["ИТОГО","","","","",
        sum(b["nights"] for b in bookings),"","",
        round(sum(b["total"] for b in bookings)),"",
        round(sum(b["total_som"] or 0 for b in bookings)),""])
    buf.seek(0)
    return buf

@app.route("/export/csv")
@login_required
def export_csv():
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM bookings ORDER BY check_in")
    bookings=[serialize_booking(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    buf=_to_csv(bookings)
    return send_file(io.BytesIO(buf.read().encode("utf-8-sig")),
        mimetype="text/csv", as_attachment=True,
        download_name=f"broni_{date.today()}.csv")

@app.route("/export/csv/<int:cottage_id>")
@login_required
def export_csv_cottage(cottage_id):
    conn=get_db(); cur=conn.cursor()
    cur.execute("SELECT * FROM cottages WHERE id=%s",(cottage_id,))
    cottage=cur.fetchone()
    if not cottage: cur.close();conn.close(); return jsonify({"error":"Не найдено"}),404
    cur.execute("SELECT * FROM bookings WHERE cottage_id=%s ORDER BY check_in",(cottage_id,))
    bookings=[serialize_booking(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    buf=_to_csv(bookings)
    return send_file(io.BytesIO(buf.read().encode("utf-8-sig")),
        mimetype="text/csv", as_attachment=True,
        download_name=f"{cottage['name']}_{date.today()}.csv")


# ── Старт ─────────────────────────────────────────────────

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"DB init skipped (no DATABASE_URL?): {e}")

@app.route("/export/excel/owner/<owner_type>")
@login_required
def export_excel_by_owner(owner_type):
    MAP = {
        "company":   ("Коттеджи",       "owner_type='Компания' AND property_type='Коттедж'"),
        "cottage":   ("Коттеджи",       "owner_type='Компания' AND property_type='Коттедж'"),
        "hotel":     ("Номера отеля",   "owner_type='Компания' AND property_type='Номер отеля'"),
        "apartment": ("Квартиры",       "owner_type='Компания' AND property_type='Квартира'"),
        "employee":  ("Сотрудники",     "owner_type='Компания' AND property_type='Номер для сотрудников'"),
        "private":   ("Собственники",   "owner_type='Собственник'"),
    }
    if owner_type not in MAP:
        return redirect(url_for("export_excel"))
    label, where_clause = MAP[owner_type]

    # ── Собственники — справочник карточек, а не брони ────
    if owner_type == "private":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM cottages WHERE owner_type = 'Собственник' ORDER BY name")
        cottages = [dict(r) for r in cur.fetchall()]
        cur.close(); conn.close()

        wb = Workbook()
        ws = wb.active
        ws.title = "Собственники"

        headers    = ["№", "Название", "Собственник", "Контакты", "Описание"]
        col_widths = [6, 28, 28, 40, 40]
        hf     = Font(bold=True, color="FFFFFF")
        hfill  = _header_fill("F59E0B")   # жёлтый акцент
        border = _thin_border()
        center = Alignment(horizontal="center", vertical="center")

        for col, (h, w) in enumerate(zip(headers, col_widths), 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font=hf; cell.fill=hfill; cell.alignment=center; cell.border=border
            ws.column_dimensions[cell.column_letter].width = w
        ws.row_dimensions[1].height = 22

        for ri, c in enumerate(cottages, 2):
            row_fill = PatternFill("solid", fgColor="FFFFFF")
            values = [ri - 1, c["name"], c.get("owner_name",""), c.get("contacts",""), c.get("description","")]
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=ri, column=col, value=val)
                cell.fill=row_fill; cell.border=border
                cell.alignment = Alignment(horizontal="center" if col==1 else "left", wrap_text=True)
            ws.row_dimensions[ri].height = 36

        ws.freeze_panes = "A2"
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"sobstvenniki_{date.today()}.xlsx")

    # ── Коттеджи / Номера отеля — брони ───────────────────
    conn = get_db(); cur = conn.cursor()
    cur.execute(f"SELECT * FROM cottages WHERE {where_clause} ORDER BY name")
    cottages = [dict(r) for r in cur.fetchall()]
    cottage_ids = [c["id"] for c in cottages]

    if cottage_ids:
        cur.execute("SELECT * FROM bookings WHERE cottage_id = ANY(%s) ORDER BY check_in", (cottage_ids,))
        all_bookings = [serialize_booking(r) for r in cur.fetchall()]
    else:
        all_bookings = []
    cur.close(); conn.close()

    wb = Workbook()
    ws = wb.active; ws.title = f"Брони — {label}"
    _write_headers(ws, row=1)
    last = _write_rows(ws, all_bookings, start=2)
    if all_bookings: _write_totals(ws, all_bookings, last + 1)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{last}"

    for c in cottages:
        ws2 = wb.create_sheet(c["name"][:28])
        ws2.merge_cells("A1:L1"); tc = ws2["A1"]
        tc.value = f"{c['name']}  |  до {c['capacity']} чел.  |  ${int(c['price_per_day'] or 0)}/сутки"
        tc.font  = Font(bold=True, size=12, color="2C3E50")
        tc.fill  = PatternFill("solid", fgColor="EEF2FF")
        tc.alignment = Alignment(horizontal="left", vertical="center")
        ws2.row_dimensions[1].height = 26
        _write_headers(ws2, row=2)
        cb   = [b for b in all_bookings if b["cottage_id"] == c["id"]]
        last = _write_rows(ws2, cb, start=3)
        if cb: _write_totals(ws2, cb, last + 1)
        ws2.freeze_panes = "A3"

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"broni_{label}_{date.today()}.xlsx")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
