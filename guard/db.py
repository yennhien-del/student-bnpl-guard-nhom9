"""Lưu trữ SQLite và kiểm tra dữ liệu nhập của Student BNPL Guard."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from guard import finance as fin

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "guard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS incomes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    date TEXT NOT NULL,
    recurring INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS fixed_costs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    category TEXT NOT NULL,
    due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),
    start_month TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS budgets(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount >= 0),
    UNIQUE(month, category)
);
CREATE TABLE IF NOT EXISTS transactions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bnpl_purchases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    item TEXT NOT NULL,
    category TEXT NOT NULL,
    purchase_date TEXT NOT NULL,
    order_value INTEGER NOT NULL CHECK(order_value > 0),
    down_payment INTEGER NOT NULL DEFAULT 0 CHECK(down_payment >= 0),
    fee INTEGER NOT NULL DEFAULT 0 CHECK(fee >= 0),
    num_installments INTEGER NOT NULL CHECK(num_installments >= 1),
    first_due_date TEXT NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bnpl_installments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES bnpl_purchases(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0)
);
CREATE TABLE IF NOT EXISTS bnpl_payments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    installment_id INTEGER NOT NULL REFERENCES bnpl_installments(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL CHECK(amount > 0),
    paid_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

TABLES = ("incomes", "fixed_costs", "budgets", "transactions",
          "bnpl_purchases", "bnpl_installments", "bnpl_payments")


# --------------------------------------------------------------------------
# Kết nối
# --------------------------------------------------------------------------
def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    path = Path(path or os.environ.get("BNPL_DB_PATH") or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_empty(conn) -> bool:
    return all(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
               for t in ("incomes", "fixed_costs", "transactions", "bnpl_purchases"))


def clear_all(conn) -> None:
    with conn:
        for t in reversed(TABLES):
            conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM settings")


# --------------------------------------------------------------------------
# Kiểm tra dữ liệu nhập
# --------------------------------------------------------------------------
def _name(v, label, maxlen=120) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError(f"{label} không được để trống.")
    if len(v) > maxlen:
        raise ValueError(f"{label} quá dài (tối đa {maxlen} ký tự).")
    return v


def _note(v) -> str:
    v = (v or "").strip()
    if len(v) > 500:
        raise ValueError("Ghi chú quá dài (tối đa 500 ký tự).")
    return v


def _money(v, label, allow_zero=False, maximum=10_000_000_000) -> int:
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        raise ValueError(f"{label} phải là số.")
    if x < 0:
        raise ValueError(f"{label} không được âm.")
    if x == 0 and not allow_zero:
        raise ValueError(f"{label} phải lớn hơn 0.")
    if x > maximum:
        raise ValueError(f"{label} quá lớn.")
    return x


def _date(v, label) -> date:
    if isinstance(v, datetime):
        v = v.date()
    if not isinstance(v, date):
        raise ValueError(f"{label} không hợp lệ.")
    return v


def _choice(v, options, label):
    if v not in options:
        raise ValueError(f"{label} không hợp lệ.")
    return v


def _insert(conn, table, values: dict) -> int:
    cols = ", ".join(values)
    ph = ", ".join("?" for _ in values)
    return conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", tuple(values.values())).lastrowid


def _update(conn, table, rid, values: dict) -> None:
    sets = ", ".join(f"{c} = ?" for c in values)
    cur = conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), rid))
    if cur.rowcount == 0:
        raise ValueError("Không tìm thấy bản ghi cần cập nhật (có thể đã bị xóa).")


def delete_row(conn, table: str, rid: int) -> None:
    if table not in TABLES:
        raise ValueError("Bảng không hợp lệ.")
    with conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (int(rid),))
    if cur.rowcount == 0:
        raise ValueError("Không tìm thấy bản ghi cần xóa.")


# --------------------------------------------------------------------------
# Thu nhập / chi phí cố định / ngân sách / giao dịch
# --------------------------------------------------------------------------
def save_income(conn, rid, name, amount, d, recurring=False, note="") -> int:
    vals = {"name": _name(name, "Tên nguồn thu"), "amount": _money(amount, "Số tiền"),
            "date": _date(d, "Ngày nhận").isoformat(), "recurring": 1 if recurring else 0,
            "note": _note(note)}
    with conn:
        if rid is None:
            return _insert(conn, "incomes", vals)
        _update(conn, "incomes", rid, vals)
        return int(rid)


def save_fixed_cost(conn, rid, name, amount, category, due_day, start_month, active=True) -> int:
    try:
        due_day = int(due_day)
    except (TypeError, ValueError):
        raise ValueError("Ngày thanh toán phải là số từ 1 đến 31.")
    if not 1 <= due_day <= 31:
        raise ValueError("Ngày thanh toán phải từ 1 đến 31.")
    if isinstance(start_month, date):
        start_month = fin.month_key(start_month)
    vals = {"name": _name(name, "Tên chi phí"), "amount": _money(amount, "Số tiền"),
            "category": _choice(category, fin.CATEGORIES, "Danh mục"), "due_day": due_day,
            "start_month": start_month, "active": 1 if active else 0}
    with conn:
        if rid is None:
            return _insert(conn, "fixed_costs", vals)
        _update(conn, "fixed_costs", rid, vals)
        return int(rid)


def save_budget(conn, month, category, amount) -> None:
    _choice(category, fin.CATEGORIES, "Danh mục")
    amount = _money(amount, "Ngân sách", allow_zero=True)
    with conn:
        conn.execute("""INSERT INTO budgets(month, category, amount) VALUES (?, ?, ?)
                        ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount""",
                     (month, category, amount))


def copy_budgets(conn, src_month: str, dst_month: str) -> int:
    rows = conn.execute("SELECT category, amount FROM budgets WHERE month = ?", (src_month,)).fetchall()
    n = 0
    with conn:
        for r in rows:
            cur = conn.execute("INSERT OR IGNORE INTO budgets(month, category, amount) VALUES (?, ?, ?)",
                               (dst_month, r["category"], r["amount"]))
            n += cur.rowcount
    return n


def save_transaction(conn, rid, name, amount, d, category, payment_method, note="") -> int:
    vals = {"name": _name(name, "Tên khoản chi"), "amount": _money(amount, "Số tiền"),
            "date": _date(d, "Ngày").isoformat(),
            "category": _choice(category, fin.CATEGORIES, "Danh mục"),
            "payment_method": _choice(payment_method, fin.PAYMENT_METHODS, "Phương thức thanh toán"),
            "note": _note(note)}
    with conn:
        if rid is None:
            return _insert(conn, "transactions", vals)
        _update(conn, "transactions", rid, vals)
        return int(rid)


# --------------------------------------------------------------------------
# BNPL
# --------------------------------------------------------------------------
def save_bnpl(conn, rid, provider, item, category, purchase_date, order_value, down_payment,
              fee, n_installments, first_due, note="") -> str:
    """Thêm/sửa khoản BNPL. Trả về 'created', 'updated' hoặc 'info_only'.

    Khi đã có thanh toán, chỉ cho sửa thông tin mô tả để không làm sai lịch sử; muốn đổi số liệu
    cần xóa khoản này và nhập lại.
    """
    provider = _name(provider, "Dịch vụ BNPL")
    item = _name(item, "Tên sản phẩm")
    category = _choice(category, fin.CATEGORIES, "Danh mục")
    purchase_date = _date(purchase_date, "Ngày mua")
    first_due = _date(first_due, "Ngày thanh toán kỳ đầu")
    if first_due < purchase_date:
        raise ValueError("Ngày thanh toán kỳ đầu không được trước ngày mua.")
    ov = _money(order_value, "Giá trị đơn hàng")
    dp = _money(down_payment, "Tiền trả trước", allow_zero=True)
    fe = _money(fee, "Phí", allow_zero=True)
    schedule = fin.build_schedule(ov, dp, fe, n_installments, first_due)
    note = _note(note)
    info = {"provider": provider, "item": item, "category": category, "note": note}
    full = {**info, "purchase_date": purchase_date.isoformat(), "order_value": ov, "down_payment": dp,
            "fee": fe, "num_installments": len(schedule), "first_due_date": first_due.isoformat()}

    def add_schedule(pid):
        for s in schedule:
            _insert(conn, "bnpl_installments", {"purchase_id": pid, "seq": s["seq"],
                                                "due_date": s["due_date"].isoformat(), "amount": s["amount"]})

    with conn:
        if rid is None:
            pid = _insert(conn, "bnpl_purchases", full)
            add_schedule(pid)
            return "created"
        has_pay = conn.execute(
            """SELECT COUNT(*) FROM bnpl_payments p JOIN bnpl_installments i ON i.id = p.installment_id
               WHERE i.purchase_id = ?""", (rid,)).fetchone()[0]
        if has_pay:
            _update(conn, "bnpl_purchases", rid, info)
            return "info_only"
        _update(conn, "bnpl_purchases", rid, full)
        conn.execute("DELETE FROM bnpl_installments WHERE purchase_id = ?", (rid,))
        add_schedule(rid)
        return "updated"


def record_payment(conn, installment_id, amount, paid_date, today: date) -> int:
    """Ghi nhận thanh toán (toàn phần hoặc một phần) cho một kỳ trả góp."""
    row = conn.execute("SELECT amount FROM bnpl_installments WHERE id = ?", (int(installment_id),)).fetchone()
    if row is None:
        raise ValueError("Không tìm thấy kỳ trả góp.")
    paid = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM bnpl_payments WHERE installment_id = ?",
                        (int(installment_id),)).fetchone()[0]
    remaining = row["amount"] - paid
    amount = _money(amount, "Số tiền thanh toán")
    paid_date = _date(paid_date, "Ngày thanh toán")
    if paid_date > today:
        raise ValueError("Ngày thanh toán không được ở tương lai.")
    if remaining <= 0:
        raise ValueError("Kỳ này đã được thanh toán đủ.")
    if amount > remaining:
        raise ValueError(f"Số tiền vượt quá phần còn nợ của kỳ này ({fin.fmt_vnd(remaining)}).")
    with conn:
        return _insert(conn, "bnpl_payments", {"installment_id": int(installment_id), "amount": amount,
                                               "paid_date": paid_date.isoformat()})


# --------------------------------------------------------------------------
# Cài đặt
# --------------------------------------------------------------------------
def get_settings(conn) -> dict:
    raw = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
    s = dict(fin.DEFAULT_SETTINGS)
    try:
        if "opening_balance" in raw:
            s["opening_balance"] = int(float(raw["opening_balance"]))
        if raw.get("balance_date"):
            s["balance_date"] = date.fromisoformat(raw["balance_date"])
        s["balance_configured"] = raw.get("balance_configured") == "1"
        for k in ("safety_buffer", "due_soon_days"):
            if k in raw:
                s[k] = int(float(raw[k]))
        for k in ("caution_ratio", "high_ratio", "budget_warn_ratio"):
            if k in raw:
                s[k] = float(raw[k])
    except ValueError:
        pass
    return s


def set_settings(conn, **values) -> None:
    cur = get_settings(conn)
    merged = {**cur, **{k: v for k, v in values.items() if v is not None}}
    if merged["safety_buffer"] < 0:
        raise ValueError("Mức đệm an toàn không được âm.")
    if not 0 < merged["caution_ratio"] < merged["high_ratio"] <= 2:
        raise ValueError("Ngưỡng «cần cân nhắc» phải lớn hơn 0 và nhỏ hơn ngưỡng «rủi ro cao».")
    if not 1 <= merged["due_soon_days"] <= 60:
        raise ValueError("Số ngày cảnh báo sắp đến hạn phải từ 1 đến 60.")
    if not 0.5 <= merged["budget_warn_ratio"] <= 1:
        raise ValueError("Ngưỡng cảnh báo ngân sách phải từ 50% đến 100%.")
    with conn:
        for k, v in values.items():
            if v is None:
                continue
            if isinstance(v, bool):
                v = "1" if v else "0"
            elif isinstance(v, date):
                v = v.isoformat()
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(v)))


def set_opening_balance(conn, amount, as_of: date) -> None:
    try:
        amount = int(round(float(amount)))
    except (TypeError, ValueError):
        raise ValueError("Số dư ban đầu phải là số.")
    set_settings(conn, opening_balance=amount, balance_date=_date(as_of, "Ngày áp dụng số dư"),
                 balance_configured=True)


# --------------------------------------------------------------------------
# Nạp dữ liệu cho tầng nghiệp vụ
# --------------------------------------------------------------------------
def load_data(conn) -> fin.FinanceData:
    def q(sql):
        return pd.read_sql_query(sql, conn)

    return fin.FinanceData.from_frames(
        incomes=q("SELECT * FROM incomes"),
        fixed_costs=q("SELECT * FROM fixed_costs"),
        budgets=q("SELECT * FROM budgets"),
        transactions=q("SELECT * FROM transactions"),
        purchases=q("SELECT * FROM bnpl_purchases"),
        installments=q("SELECT * FROM bnpl_installments"),
        payments=q("SELECT * FROM bnpl_payments"),
        settings=get_settings(conn),
    )
