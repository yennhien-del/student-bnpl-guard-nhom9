"""Dữ liệu demo cho Student BNPL Guard.

Chạy trực tiếp:  python -m guard.seed        (chỉ nạp khi CSDL đang trống)
                 python -m guard.seed --force (xóa dữ liệu cũ rồi nạp lại)
Dữ liệu được sinh tương đối theo ngày hôm nay nên luôn có kỳ quá hạn / sắp đến hạn để minh họa.
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta

from guard import db, finance as fin

NAMES = {
    "Ăn uống": ["Cơm trưa căng tin", "Bún bò", "Trà sữa", "Cà phê", "Bánh mì", "Ăn tối với bạn", "Mì cay"],
    "Đi lại": ["Xe buýt", "Grab đi học", "Xăng xe", "Gửi xe"],
    "Học tập": ["Photo giáo trình", "Sách tham khảo", "Văn phòng phẩm"],
    "Mua sắm": ["Áo thun", "Đồ dùng phòng trọ", "Mỹ phẩm", "Phụ kiện điện thoại"],
    "Giải trí": ["Xem phim", "Game online", "Đi chơi cuối tuần", "Karaoke"],
    "Sức khỏe": ["Thuốc cảm", "Khám răng"],
    "Khác": ["Quà sinh nhật bạn", "Sửa điện thoại", "Cắt tóc"],
}
RANGES = {"Ăn uống": (35_000, 90_000), "Đi lại": (15_000, 60_000), "Học tập": (30_000, 150_000),
          "Mua sắm": (80_000, 300_000), "Giải trí": (50_000, 200_000),
          "Sức khỏe": (40_000, 250_000), "Khác": (30_000, 150_000)}
BUDGETS = {"Ăn uống": 2_000_000, "Đi lại": 500_000, "Nhà ở": 2_200_000, "Học tập": 500_000,
           "Mua sắm": 600_000, "Giải trí": 500_000, "Sức khỏe": 200_000, "Khác": 300_000}


def seed_demo(conn, today: date | None = None, force: bool = False) -> bool:
    today = today or date.today()
    if not force and not db.is_empty(conn):
        return False
    db.clear_all(conn)
    rng = random.Random(2026)
    cur = fin.month_key(today)
    first_m = fin.add_months(cur, -3)
    anchor = fin.month_start(first_m)

    db.set_opening_balance(conn, 2_500_000, anchor)
    db.save_income(conn, None, "Gia đình gửi hàng tháng", 5_000_000, anchor, True, "Sinh hoạt phí")
    db.save_income(conn, None, "Dạy kèm / làm thêm", 1_500_000, anchor.replace(day=10), True, "")
    db.save_fixed_cost(conn, None, "Tiền trọ", 2_000_000, "Nhà ở", 5, first_m)
    db.save_fixed_cost(conn, None, "Internet & điện thoại", 150_000, "Khác", 12, first_m)
    db.save_fixed_cost(conn, None, "Gói học tiếng Anh online", 200_000, "Học tập", 20, first_m)

    for k in range(-3, 2):
        for cat, amt in BUDGETS.items():
            db.save_budget(conn, fin.add_months(cur, k), cat, amt)

    d = anchor
    while d <= today:
        if rng.random() < 0.8:
            _txn(conn, rng, d, "Ăn uống")
        if rng.random() < 0.08:
            _txn(conn, rng, d, "Ăn uống", big=True)
        if rng.random() < 0.3:
            _txn(conn, rng, d, "Đi lại")
        if rng.random() < 0.09:
            _txn(conn, rng, d, "Giải trí")
        if rng.random() < 0.04:
            _txn(conn, rng, d, "Mua sắm")
        if rng.random() < 0.1:
            _txn(conn, rng, d, "Học tập")
        if rng.random() < 0.03:
            _txn(conn, rng, d, "Sức khỏe")
        if rng.random() < 0.05:
            _txn(conn, rng, d, "Khác")
        d += timedelta(days=1)

    # --- BNPL ---
    # A: đã trả kỳ 1, kỳ 2 trả một phần (nếu đã đến hạn), kỳ 3 chưa tới
    first_due_a = fin.clamp_day(fin.add_months(cur, -1), 10)
    db.save_bnpl(conn, None, "Shopee SPayLater", "Tai nghe Bluetooth", "Mua sắm",
                 fin.clamp_day(fin.add_months(cur, -2), 8), 1_500_000, 0, 45_000, 3, first_due_a,
                 "Mua trong đợt sale")
    pid_a = conn.execute("SELECT id FROM bnpl_purchases WHERE item = 'Tai nghe Bluetooth'").fetchone()[0]
    inst = conn.execute("SELECT id, amount, due_date FROM bnpl_installments WHERE purchase_id = ? ORDER BY seq",
                        (pid_a,)).fetchall()
    db.record_payment(conn, inst[0]["id"], inst[0]["amount"], first_due_a, today)
    due2 = date.fromisoformat(inst[1]["due_date"])
    if due2 <= today:
        db.record_payment(conn, inst[1]["id"], 300_000, due2, today)

    # B: kỳ 1 đã quá hạn, chưa trả
    db.save_bnpl(conn, None, "Shopee SPayLater", "Bàn phím cơ", "Mua sắm", today - timedelta(days=40),
                 900_000, 0, 27_000, 2, today - timedelta(days=10), "")
    # C: có trả trước, kỳ 1 sắp đến hạn
    db.save_bnpl(conn, None, "Home PayLater", "Giày thể thao", "Mua sắm", today - timedelta(days=7),
                 1_800_000, 300_000, 60_000, 4, today + timedelta(days=5), "Trả trước 300.000 ₫")
    return True


def _txn(conn, rng, d, cat, big=False):
    lo, hi = RANGES[cat]
    if big:
        lo, hi = 120_000, 220_000
    amt = int(round(rng.uniform(lo, hi) / 1000.0) * 1000)
    db.save_transaction(conn, None, rng.choice(NAMES[cat]), amt, d, cat,
                        rng.choice(fin.PAYMENT_METHODS), "")


if __name__ == "__main__":
    c = db.connect()
    db.init_db(c)
    ok = seed_demo(c, force="--force" in sys.argv)
    print("Đã nạp dữ liệu demo." if ok else "CSDL đã có dữ liệu. Dùng --force để nạp lại (sẽ xóa dữ liệu cũ).")
