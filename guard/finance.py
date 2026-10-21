"""Lõi nghiệp vụ tài chính của Student BNPL Guard.

Thuần Python/pandas, không phụ thuộc Streamlit hay SQLite để dễ kiểm thử.
Quy ước: tiền là số nguyên VNĐ, ngày là ``datetime.date``.

Nguyên tắc chống tính trùng
---------------------------
* Giá trị đơn hàng BNPL KHÔNG bao giờ được ghi là chi tiêu.
* Chi tiêu thực tế (cơ sở tiền mặt) chỉ gồm tiền đã thực sự ra khỏi tài khoản:
  giao dịch hằng ngày, chi phí cố định đã đến hạn, tiền trả trước BNPL và các
  khoản đã thanh toán cho từng kỳ trả góp (kể cả thanh toán một phần).
* Khoản dự kiến (kỳ chưa trả, chi phí cố định chưa đến hạn, thu nhập chưa nhận,
  chi tiêu biến đổi ước tính) chỉ xuất hiện trong dự báo, không vào chi tiêu thực tế.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

# --------------------------------------------------------------------------
# Hằng số
# --------------------------------------------------------------------------
CATEGORIES = ["Ăn uống", "Đi lại", "Nhà ở", "Học tập", "Mua sắm", "Giải trí", "Sức khỏe", "Khác"]
PAYMENT_METHODS = ["Tiền mặt", "Chuyển khoản", "Thẻ ngân hàng", "Ví điện tử"]
BNPL_PROVIDERS = ["Shopee SPayLater", "Home PayLater", "MoMo Trả Sau", "Fundiin", "Khác"]

# Ngưỡng rủi ro do ứng dụng tự thiết lập (người dùng có thể chỉnh trong Cài đặt).
# Đây KHÔNG phải chuẩn tài chính chính thức.
DEFAULT_SETTINGS = {
    "opening_balance": 0,
    "balance_date": None,
    "balance_configured": False,
    "safety_buffer": 500_000,   # số dư tối thiểu nên giữ lại
    "caution_ratio": 0.5,       # nghĩa vụ cố định + BNPL / thu nhập tháng -> "cần cân nhắc"
    "high_ratio": 0.7,          # -> "rủi ro cao"
    "due_soon_days": 7,
    "budget_warn_ratio": 0.8,
}

RISK_LABELS = {
    "low": "Rủi ro thấp",
    "caution": "Cần cân nhắc",
    "high": "Rủi ro cao",
    "insufficient": "Chưa đủ dữ liệu",
}

COLUMNS = {
    "incomes": ["id", "name", "amount", "date", "recurring", "note"],
    "fixed_costs": ["id", "name", "amount", "category", "due_day", "start_month", "active"],
    "budgets": ["id", "month", "category", "amount"],
    "transactions": ["id", "name", "amount", "date", "category", "payment_method", "note"],
    "purchases": ["id", "provider", "item", "category", "purchase_date", "order_value",
                  "down_payment", "fee", "num_installments", "first_due_date", "note"],
    "installments": ["id", "purchase_id", "seq", "due_date", "amount"],
    "payments": ["id", "installment_id", "amount", "paid_date"],
}
DATE_COLUMNS = {
    "incomes": ["date"], "transactions": ["date"],
    "purchases": ["purchase_date", "first_due_date"],
    "installments": ["due_date"], "payments": ["paid_date"],
}
LEDGER_COLS = ["date", "name", "amount", "category", "source"]


# --------------------------------------------------------------------------
# Định dạng và ngày tháng
# --------------------------------------------------------------------------
def fmt_vnd(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"{int(round(float(x))):,}".replace(",", ".") + " ₫"


def fmt_date(d) -> str:
    d = to_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def fmt_month(m: str) -> str:
    y, mo = m.split("-")
    return f"Tháng {int(mo):02d}/{y}"


def to_date(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    return date.fromisoformat(s[:10]) if s else None


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_start(m: str) -> date:
    y, mo = map(int, m.split("-"))
    return date(y, mo, 1)


def month_end(m: str) -> date:
    y, mo = map(int, m.split("-"))
    return date(y, mo, calendar.monthrange(y, mo)[1])


def add_months(m: str, n: int) -> str:
    y, mo = map(int, m.split("-"))
    idx = y * 12 + (mo - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(start: date, end: date) -> list[str]:
    out, m, last = [], month_key(start), month_key(end)
    while m <= last:
        out.append(m)
        m = add_months(m, 1)
    return out


def clamp_day(m: str, day: int) -> date:
    y, mo = map(int, m.split("-"))
    return date(y, mo, min(int(day), calendar.monthrange(y, mo)[1]))


def _between(series: pd.Series, start: date, end: date) -> pd.Series:
    return pd.Series([start <= d <= end for d in series], index=series.index, dtype=bool)


def _sum(events) -> float:
    return float(sum(e[2] for e in events))


# --------------------------------------------------------------------------
# Dữ liệu
# --------------------------------------------------------------------------
@dataclass
class FinanceData:
    incomes: pd.DataFrame
    fixed_costs: pd.DataFrame
    budgets: pd.DataFrame
    transactions: pd.DataFrame
    purchases: pd.DataFrame
    installments: pd.DataFrame   # đã bổ sung paid_amount, remaining, item, provider, category
    payments: pd.DataFrame       # đã bổ sung seq, item, provider, category
    settings: dict

    @classmethod
    def from_frames(cls, incomes=None, fixed_costs=None, budgets=None, transactions=None,
                    purchases=None, installments=None, payments=None, settings=None):
        raw = {"incomes": incomes, "fixed_costs": fixed_costs, "budgets": budgets,
               "transactions": transactions, "purchases": purchases,
               "installments": installments, "payments": payments}
        frames = {}
        for name, cols in COLUMNS.items():
            df = raw[name]
            df = pd.DataFrame(columns=cols) if df is None else df.copy()
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            df = df[cols].reset_index(drop=True)
            for c in DATE_COLUMNS.get(name, []):
                df[c] = [to_date(v) for v in df[c]]
            frames[name] = df
        for name, col in (("incomes", "amount"), ("fixed_costs", "amount"), ("budgets", "amount"),
                          ("transactions", "amount"), ("installments", "amount"), ("payments", "amount")):
            frames[name][col] = pd.to_numeric(frames[name][col])
        for col in ("order_value", "down_payment", "fee"):
            frames["purchases"][col] = pd.to_numeric(frames["purchases"][col])

        pay, inst, pur = frames["payments"], frames["installments"], frames["purchases"]
        paid = pay.groupby("installment_id")["amount"].sum() if len(pay) else pd.Series(dtype=float)
        inst["paid_amount"] = pd.to_numeric(inst["id"].map(paid), errors="coerce").fillna(0.0)
        inst["remaining"] = inst["amount"] - inst["paid_amount"]
        pmeta = pur[["id", "provider", "item", "category"]].rename(columns={"id": "purchase_id"})
        inst = inst.merge(pmeta, on="purchase_id", how="left")
        imeta = inst[["id", "seq", "purchase_id", "item", "provider", "category"]].rename(
            columns={"id": "installment_id"})
        pay = pay.merge(imeta, on="installment_id", how="left")
        frames["installments"], frames["payments"] = inst, pay
        return cls(settings={**DEFAULT_SETTINGS, **(settings or {})}, **frames)

    def is_empty(self) -> bool:
        return all(len(df) == 0 for df in (self.incomes, self.fixed_costs, self.transactions,
                                           self.purchases))


# --------------------------------------------------------------------------
# Lịch trả góp BNPL
# --------------------------------------------------------------------------
def add_months_date(d: date, n: int, day: int | None = None) -> date:
    return clamp_day(add_months(month_key(d), n), day or d.day)


def build_schedule(order_value, down_payment, fee, n_installments, first_due: date) -> list[dict]:
    """Tạo lịch trả góp.

    Tổng phải trả sau khi mua = tiền trả trước + (giá trị đơn hàng - trả trước + phí).
    Phần thanh toán chia đều cho các kỳ; số dư lẻ (VNĐ) cộng vào kỳ cuối.
    Phí là tổng phí (VNĐ) cả kỳ hạn, không nhân thêm theo từng kỳ.
    """
    try:
        order_value, down_payment, fee = (int(round(float(x))) for x in (order_value, down_payment, fee))
        n = int(n_installments)
    except (TypeError, ValueError):
        raise ValueError("Giá trị đơn hàng, tiền trả trước, phí và số kỳ phải là số.")
    if order_value <= 0:
        raise ValueError("Giá trị đơn hàng phải lớn hơn 0.")
    if down_payment < 0 or fee < 0:
        raise ValueError("Tiền trả trước và phí không được âm.")
    if down_payment >= order_value:
        raise ValueError("Tiền trả trước phải nhỏ hơn giá trị đơn hàng (nếu trả đủ ngay thì đó không phải BNPL).")
    if not 1 <= n <= 60:
        raise ValueError("Số kỳ phải từ 1 đến 60.")
    first_due = to_date(first_due)
    if first_due is None:
        raise ValueError("Cần chọn ngày thanh toán kỳ đầu tiên.")
    total = (order_value - down_payment) + fee
    base = total // n
    amounts = [base] * n
    amounts[-1] += total - base * n
    return [{"seq": i + 1, "due_date": add_months_date(first_due, i, first_due.day), "amount": amounts[i]}
            for i in range(n)]


def installment_status(amount, paid, due_date, today, due_soon_days=7) -> str:
    remaining = float(amount) - float(paid)
    if remaining <= 0:
        return "Đã thanh toán"
    if due_date < today:
        return "Quá hạn"
    if paid > 0:
        return "Trả một phần"
    if (due_date - today).days <= due_soon_days:
        return "Sắp đến hạn"
    return "Chưa đến hạn"


def installments_view(data: FinanceData, today: date) -> pd.DataFrame:
    inst = data.installments.copy()
    ds = int(data.settings["due_soon_days"])
    inst["days_to_due"] = [(d - today).days for d in inst["due_date"]]
    inst["status"] = [installment_status(a, p, d, today, ds)
                      for a, p, d in zip(inst["amount"], inst["paid_amount"], inst["due_date"])]
    return inst


def purchase_summary(data: FinanceData) -> pd.DataFrame:
    """Mỗi khoản BNPL: tổng phải trả, đã trả, còn nợ."""
    rows = []
    for p in data.purchases.to_dict("records"):
        inst = data.installments[data.installments["purchase_id"] == p["id"]]
        total_inst = float(inst["amount"].sum())
        paid_inst = float(inst["paid_amount"].sum())
        rows.append({
            "id": p["id"], "provider": p["provider"], "item": p["item"], "category": p["category"],
            "purchase_date": p["purchase_date"], "order_value": float(p["order_value"]),
            "down_payment": float(p["down_payment"]), "fee": float(p["fee"]),
            "num_installments": int(p["num_installments"]),
            "total_payable": float(p["down_payment"]) + total_inst,
            "paid": float(p["down_payment"]) + paid_inst,
            "remaining": float(inst["remaining"].sum()),
        })
    cols = ["id", "provider", "item", "category", "purchase_date", "order_value", "down_payment",
            "fee", "num_installments", "total_payable", "paid", "remaining"]
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# Sự kiện lặp: thu nhập, chi phí cố định
# --------------------------------------------------------------------------
def income_events(incomes: pd.DataFrame, start: date, end: date) -> list[tuple]:
    out: list[tuple] = []
    if start > end or incomes is None or len(incomes) == 0:
        return out
    for r in incomes.to_dict("records"):
        d0, amt = r["date"], float(r["amount"])
        if int(r.get("recurring") or 0):
            for m in months_between(start, end):
                d = clamp_day(m, d0.day)
                if d >= d0 and start <= d <= end:
                    out.append((d, r["name"], amt))
        elif start <= d0 <= end:
            out.append((d0, r["name"], amt))
    return sorted(out, key=lambda e: e[0])


def fixed_events(fixed: pd.DataFrame, start: date, end: date) -> list[tuple]:
    out: list[tuple] = []
    if start > end or fixed is None or len(fixed) == 0:
        return out
    for r in fixed.to_dict("records"):
        if not int(r.get("active") if r.get("active") is not None else 1):
            continue
        first = r.get("start_month") or "0000-00"
        for m in months_between(start, end):
            if m < first:
                continue
            d = clamp_day(m, r["due_day"])
            if start <= d <= end:
                out.append((d, r["name"], float(r["amount"]), r["category"]))
    return sorted(out, key=lambda e: e[0])


# --------------------------------------------------------------------------
# Sổ chi tiêu thực tế (cơ sở tiền mặt)
# --------------------------------------------------------------------------
def build_ledger(data: FinanceData, start: date, end: date, today: date) -> pd.DataFrame:
    """Mọi khoản tiền đã thực sự chi ra trong [start, min(end, today)]."""
    end = min(end, today)
    if start > end:
        return pd.DataFrame(columns=LEDGER_COLS)
    rows = []
    t = data.transactions
    if len(t):
        for r in t[_between(t["date"], start, end)].to_dict("records"):
            rows.append((r["date"], r["name"], float(r["amount"]), r["category"], "Giao dịch"))
    for d, name, amt, cat in fixed_events(data.fixed_costs, start, end):
        rows.append((d, name, amt, cat, "Chi phí cố định"))
    p = data.purchases
    if len(p):
        for r in p[_between(p["purchase_date"], start, end)].to_dict("records"):
            if float(r["down_payment"]) > 0:
                rows.append((r["purchase_date"], f"Trả trước: {r['item']}", float(r["down_payment"]),
                             r["category"], "BNPL – trả trước"))
    pay = data.payments
    if len(pay):
        for r in pay[_between(pay["paid_date"], start, end)].to_dict("records"):
            rows.append((r["paid_date"], f"Kỳ {int(r['seq'])}: {r['item']}", float(r["amount"]),
                         r["category"], "BNPL – trả góp"))
    df = pd.DataFrame(rows, columns=LEDGER_COLS)
    if len(df):
        df = df.sort_values("date", ascending=False, kind="stable").reset_index(drop=True)
    return df


def _anchor(data: FinanceData, ref: date) -> date:
    d = data.settings.get("balance_date")
    return d if isinstance(d, date) else month_start(month_key(ref))


def balance_as_of(data: FinanceData, as_of: date) -> float:
    """Số dư thực tế tại cuối ngày ``as_of`` = số dư ban đầu + thu đã nhận - chi đã phát sinh."""
    opening = float(data.settings.get("opening_balance") or 0)
    anchor = _anchor(data, as_of)
    if as_of < anchor:
        return opening
    income = _sum(income_events(data.incomes, anchor, as_of))
    led = build_ledger(data, anchor, as_of, as_of)
    out = float(led["amount"].sum()) if len(led) else 0.0
    return opening + income - out


# --------------------------------------------------------------------------
# Dự báo dòng tiền
# --------------------------------------------------------------------------
@dataclass
class MonthProjection:
    month: str
    opening: float
    income: float          # thu nhập còn sẽ nhận trong tháng
    income_full: float     # thu nhập cả tháng (dùng tính tỷ lệ nghĩa vụ)
    fixed: float           # chi phí cố định còn phải trả
    fixed_full: float
    bnpl_existing: float   # kỳ BNPL hiện có còn phải trả (gồm cả quá hạn ở tháng hiện tại)
    bnpl_new: float        # kỳ BNPL của khoản mua đang xét
    variable: float        # chi tiêu biến đổi ước tính còn lại
    closing: float         # số dư dự kiến cuối tháng

    @property
    def obligations(self) -> float:
        return self.fixed_full + self.bnpl_existing + self.bnpl_new

    @property
    def ratio(self):
        return self.obligations / self.income_full if self.income_full > 0 else None


def variable_spend_estimate(data: FinanceData, month: str, today: date) -> tuple[float, str]:
    """Ước tính chi tiêu biến đổi (giao dịch hằng ngày) cho một tháng."""
    cur = month_key(today)
    t = data.transactions
    sums = []
    for k in (1, 2, 3):
        m = add_months(cur, -k)
        vals = t[_between(t["date"], month_start(m), month_end(m))]["amount"] if len(t) else []
        if len(vals):
            sums.append(float(sum(vals)))
    if sums:
        return sum(sums) / len(sums), "trung bình các tháng gần nhất"
    b = data.budgets
    bm = b[b["month"] == month]
    if bm.empty:
        bm = b[b["month"] == cur]
    if len(bm):
        fixed_by_cat: dict[str, float] = {}
        for _, _, amt, cat in fixed_events(data.fixed_costs, month_start(month), month_end(month)):
            fixed_by_cat[cat] = fixed_by_cat.get(cat, 0.0) + amt
        est = sum(max(0.0, float(r["amount"]) - fixed_by_cat.get(r["category"], 0.0))
                  for r in bm.to_dict("records"))
        return est, "ngân sách đã đặt"
    return 0.0, "chưa có dữ liệu"


def project(data: FinanceData, today: date, n_months: int = 3, extra_cash_now: float = 0.0,
            extra_schedule: list[dict] | None = None) -> list[MonthProjection]:
    cur = month_key(today)
    bal = balance_as_of(data, today) - float(extra_cash_now)
    inst = data.installments
    inst_open = inst[inst["remaining"] > 0] if len(inst) else inst
    extra = extra_schedule or []
    t = data.transactions
    spent_var = 0.0
    if len(t):
        spent_var = float(t[_between(t["date"], month_start(cur), today)]["amount"].sum())
    out = []
    for i in range(n_months):
        m = add_months(cur, i)
        ms, me = month_start(m), month_end(m)
        lo = today + timedelta(days=1) if i == 0 else ms
        income = _sum(income_events(data.incomes, lo, me))
        fixed = _sum(fixed_events(data.fixed_costs, lo, me))
        income_full = _sum(income_events(data.incomes, ms, me))
        fixed_full = _sum(fixed_events(data.fixed_costs, ms, me))

        def due(d, ms=ms, me=me, i=i):
            return d <= me if i == 0 else ms <= d <= me

        bn_exist = float(sum(r for r, d in zip(inst_open["remaining"], inst_open["due_date"]) if due(d))) \
            if len(inst_open) else 0.0
        bn_new = float(sum(s["amount"] for s in extra if due(s["due_date"])))
        est, _ = variable_spend_estimate(data, m, today)
        variable = max(0.0, est - spent_var) if i == 0 else est
        closing = bal + income - fixed - bn_exist - bn_new - variable
        out.append(MonthProjection(m, bal, income, income_full, fixed, fixed_full,
                                   bn_exist, bn_new, variable, closing))
        bal = closing
    return out


# --------------------------------------------------------------------------
# Kiểm tra trước khi mua
# --------------------------------------------------------------------------
def classify_risk(current_balance: float, immediate: float, after: list[MonthProjection],
                  has_income: bool, balance_configured: bool, settings: dict):
    """Quy tắc minh bạch. Các ngưỡng do ứng dụng tự thiết lập, không phải chuẩn chính thức."""
    s = {**DEFAULT_SETTINGS, **settings}
    reasons: list[str] = []
    if not balance_configured:
        return "insufficient", ["Chưa thiết lập số dư ban đầu (vào Cài đặt) nên chưa thể tính số dư dự kiến."]
    if not has_income:
        return "insufficient", ["Chưa có nguồn thu nhập nào để dự báo dòng tiền (vào Ngân sách → Thu nhập)."]
    rank = {"low": 0, "caution": 1, "high": 2}
    level = "low"

    def bump(l):
        nonlocal level
        if rank[l] > rank[level]:
            level = l

    if immediate > current_balance:
        bump("high")
        reasons.append(f"Số tiền phải trả ngay ({fmt_vnd(immediate)}) lớn hơn số dư hiện tại ({fmt_vnd(current_balance)}).")
    low = min(after, key=lambda p: p.closing)
    if low.closing < 0:
        bump("high")
        reasons.append(f"Số dư dự kiến cuối {fmt_month(low.month).lower()} âm ({fmt_vnd(low.closing)}).")
    elif low.closing < s["safety_buffer"]:
        bump("caution")
        reasons.append(f"Số dư dự kiến thấp nhất ({fmt_vnd(low.closing)} vào cuối {fmt_month(low.month).lower()}) "
                       f"thấp hơn mức đệm an toàn bạn đặt ({fmt_vnd(s['safety_buffer'])}).")
    worst = None
    for p in after:
        r = p.ratio
        if r is not None and (worst is None or r > worst[1]):
            worst = (p, r)
    if worst:
        p, r = worst
        if r > s["high_ratio"]:
            bump("high")
            reasons.append(f"{fmt_month(p.month)}: nghĩa vụ cố định + BNPL chiếm {r:.0%} thu nhập "
                           f"(ngưỡng cao {s['high_ratio']:.0%}).")
        elif r > s["caution_ratio"]:
            bump("caution")
            reasons.append(f"{fmt_month(p.month)}: nghĩa vụ cố định + BNPL chiếm {r:.0%} thu nhập "
                           f"(ngưỡng cân nhắc {s['caution_ratio']:.0%}).")
    for p in after:
        if p.income_full == 0 and (p.fixed_full + p.bnpl_existing + p.bnpl_new) > 0:
            reasons.append(f"{fmt_month(p.month)} chưa có thu nhập dự kiến; hãy đánh dấu nguồn thu định kỳ nếu có.")
            break
    if level == "low":
        reasons.insert(0, f"Số dư dự kiến thấp nhất sau khi mua là {fmt_vnd(low.closing)} "
                          f"({fmt_month(low.month).lower()}), vẫn trên mức đệm an toàn.")
    return level, reasons


def assess_purchase(data: FinanceData, today: date, item: str, order_value, mode: str,
                    down_payment=0, fee=0, n_installments=1, first_due: date | None = None) -> dict:
    """mode: 'cash' (trả ngay) hoặc 'bnpl' (trả góp)."""
    item = (item or "").strip() or "Sản phẩm dự kiến mua"
    try:
        ov = int(round(float(order_value)))
    except (TypeError, ValueError):
        raise ValueError("Giá trị đơn hàng phải là số.")
    if ov <= 0:
        raise ValueError("Giá trị đơn hàng phải lớn hơn 0.")
    if mode == "cash":
        schedule, immediate = [], float(ov)
    elif mode == "bnpl":
        schedule = build_schedule(ov, down_payment, fee, n_installments, first_due)
        immediate = float(int(round(float(down_payment))))
    else:
        raise ValueError("Phương án thanh toán không hợp lệ.")
    cur = month_key(today)
    horizon = 3
    if schedule:
        horizon = max(3, len(months_between(today, schedule[-1]["due_date"])) + 1)
    horizon = min(horizon, 14)
    before = project(data, today, horizon)
    after = project(data, today, horizon, extra_cash_now=immediate, extra_schedule=schedule)
    current_balance = balance_as_of(data, today)
    level, reasons = classify_risk(current_balance, immediate, after, len(data.incomes) > 0,
                                   bool(data.settings.get("balance_configured")), data.settings)
    est, src = variable_spend_estimate(data, cur, today)
    notes = [f"Chi tiêu biến đổi được ước tính theo {src}."]
    if src == "chưa có dữ liệu":
        notes.append("Chưa có lịch sử chi tiêu hay ngân sách nên khoản chi biến đổi tính bằng 0; kết quả có thể quá lạc quan.")
    return {
        "item": item, "order_value": ov, "mode": mode, "immediate": immediate,
        "schedule": schedule, "current_balance": current_balance,
        "before": before, "after": after, "level": level, "label": RISK_LABELS[level],
        "reasons": reasons, "notes": notes,
        "inputs": {"down_payment": down_payment, "fee": fee, "n": n_installments, "first_due": first_due},
    }


def summarize_assessment(res: dict) -> dict:
    """Bản tóm tắt dạng JSON để gửi cho AI (số liệu do Python tính)."""
    return {
        "san_pham": res["item"], "gia_tri_don_hang": res["order_value"],
        "phuong_an": "Trả ngay" if res["mode"] == "cash" else "BNPL trả góp",
        "tien_tra_ngay": int(res["immediate"]),
        "so_du_hien_tai": int(res["current_balance"]),
        "muc_do_rui_ro": res["label"], "ly_do": res["reasons"],
        "lich_tra_gop": [{"ky": s["seq"], "han": fmt_date(s["due_date"]), "so_tien": int(s["amount"])}
                         for s in res["schedule"]],
        "theo_thang": [{
            "thang": a.month,
            "nghia_vu_co_dinh": int(a.fixed_full), "bnpl_hien_co": int(a.bnpl_existing),
            "bnpl_moi": int(a.bnpl_new), "so_du_cuoi_thang_truoc_khi_mua": int(b.closing),
            "so_du_cuoi_thang_sau_khi_mua": int(a.closing),
        } for b, a in zip(res["before"], res["after"])],
    }


# --------------------------------------------------------------------------
# Tổng hợp tháng, ngân sách, cảnh báo
# --------------------------------------------------------------------------
def month_summary(data: FinanceData, month: str, today: date) -> dict:
    ms, me = month_start(month), month_end(month)
    cur = month_key(today)
    inc = income_events(data.incomes, ms, me)
    led = build_ledger(data, ms, me, today)
    by_cat = led.groupby("category")["amount"].sum().sort_values(ascending=False) if len(led) \
        else pd.Series(dtype=float)
    by_src = led.groupby("source")["amount"].sum() if len(led) else pd.Series(dtype=float)
    iv = installments_view(data, today)
    open_ = iv[iv["remaining"] > 0]
    if month >= cur:
        due_mask = [d <= me for d in open_["due_date"]]
    else:
        due_mask = [ms <= d <= me for d in open_["due_date"]]
    bnpl_due = float(open_[due_mask]["remaining"].sum()) if len(open_) else 0.0
    overdue = open_[[d < today for d in open_["due_date"]]] if len(open_) else open_
    lo = max(today + timedelta(days=1), ms)
    return {
        "month": month,
        "income_total": _sum(inc),
        "income_received": _sum([e for e in inc if e[0] <= today]),
        "spend_actual": float(led["amount"].sum()) if len(led) else 0.0,
        "spend_by_category": by_cat,
        "spend_by_source": by_src,
        "fixed_remaining": _sum(fixed_events(data.fixed_costs, lo, me)) if lo <= me else 0.0,
        "bnpl_remaining_total": float(open_["remaining"].sum()) if len(open_) else 0.0,
        "bnpl_open_count": int(len(open_)),
        "bnpl_due_month": bnpl_due,
        "bnpl_overdue": float(overdue["remaining"].sum()) if len(overdue) else 0.0,
        "bnpl_overdue_count": int(len(overdue)),
    }


def budget_usage(data: FinanceData, month: str, today: date) -> pd.DataFrame:
    cols = ["category", "budget", "actual", "remaining", "pct", "status"]
    b = data.budgets[data.budgets["month"] == month]
    if b.empty:
        return pd.DataFrame(columns=cols)
    led = build_ledger(data, month_start(month), month_end(month), today)
    actual = led.groupby("category")["amount"].sum() if len(led) else pd.Series(dtype=float)
    warn = float(data.settings["budget_warn_ratio"])
    rows = []
    for r in b.to_dict("records"):
        a, bud = float(actual.get(r["category"], 0.0)), float(r["amount"])
        pct = a / bud if bud > 0 else (float("inf") if a > 0 else 0.0)
        status = "Vượt ngân sách" if pct > 1 else ("Gần hết" if pct >= warn else "Trong ngân sách")
        rows.append({"category": r["category"], "budget": bud, "actual": a,
                     "remaining": bud - a, "pct": pct, "status": status})
    df = pd.DataFrame(rows, columns=cols)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return df.sort_values("category", key=lambda s: s.map(lambda c: order.get(c, 99))).reset_index(drop=True)


def build_alerts(data: FinanceData, today: date, month: str) -> list[dict]:
    alerts: list[dict] = []
    s = data.settings
    if not s["balance_configured"]:
        alerts.append({"level": "info", "text": "Bạn chưa thiết lập số dư ban đầu. Vào Cài đặt để nhập, "
                                                "nếu không số dư hiện tại và dự báo sẽ chưa chính xác."})
    iv = installments_view(data, today)
    open_ = iv[iv["remaining"] > 0].sort_values("due_date")
    for r in open_.to_dict("records"):
        if r["days_to_due"] < 0:
            alerts.append({"level": "danger", "text":
                           f"Quá hạn {-r['days_to_due']} ngày: {r['item']} – kỳ {int(r['seq'])}, còn {fmt_vnd(r['remaining'])} "
                           f"(hạn {fmt_date(r['due_date'])})."})
        elif r["days_to_due"] <= int(s["due_soon_days"]):
            alerts.append({"level": "warning", "text":
                           f"Sắp đến hạn ({fmt_date(r['due_date'])}): {r['item']} – kỳ {int(r['seq'])}, còn {fmt_vnd(r['remaining'])}."})
    for r in budget_usage(data, month, today).to_dict("records"):
        if r["status"] == "Vượt ngân sách":
            alerts.append({"level": "danger", "text":
                           f"Vượt ngân sách «{r['category']}»: đã chi {fmt_vnd(r['actual'])} / {fmt_vnd(r['budget'])}."})
        elif r["status"] == "Gần hết":
            alerts.append({"level": "warning", "text":
                           f"Sắp hết ngân sách «{r['category']}»: đã dùng {r['pct']:.0%} ({fmt_vnd(r['actual'])} / {fmt_vnd(r['budget'])})."})
    if s["balance_configured"]:
        cur_proj = project(data, today, 1)[0]
        if cur_proj.closing < 0:
            alerts.append({"level": "danger", "text":
                           f"Số dư dự kiến cuối tháng này âm ({fmt_vnd(cur_proj.closing)}). Cần giảm chi hoặc chuẩn bị thêm tiền."})
        elif cur_proj.closing < s["safety_buffer"]:
            alerts.append({"level": "warning", "text":
                           f"Số dư dự kiến cuối tháng ({fmt_vnd(cur_proj.closing)}) thấp hơn mức đệm an toàn {fmt_vnd(s['safety_buffer'])}."})
        if balance_as_of(data, today) < 0:
            alerts.append({"level": "danger", "text": "Số dư hiện tại đang âm. Hãy kiểm tra lại số dư ban đầu và các khoản đã ghi."})
    if not alerts:
        alerts.append({"level": "success", "text": "Chưa có cảnh báo. Tình hình tài chính trong tháng đang ổn."})
    order = {"danger": 0, "warning": 1, "info": 2, "success": 3}
    return sorted(alerts, key=lambda a: order[a["level"]])


# --------------------------------------------------------------------------
# Thống kê / báo cáo
# --------------------------------------------------------------------------
def aggregate_spending(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """freq: 'D' ngày, 'W' tuần (bắt đầu thứ Hai), 'M' tháng."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["period", "label", "amount"])
    dts = pd.to_datetime(pd.Series(list(df["date"])))
    if freq == "D":
        p = dts.dt.normalize()
    elif freq == "W":
        p = (dts - pd.to_timedelta(dts.dt.dayofweek, unit="D")).dt.normalize()
    elif freq == "M":
        p = dts.dt.to_period("M").dt.to_timestamp()
    else:
        raise ValueError("freq phải là D, W hoặc M")
    g = pd.DataFrame({"period": p, "amount": list(df["amount"].astype(float))})
    g = g.groupby("period", as_index=False)["amount"].sum().sort_values("period")
    fmt = {"D": "%d/%m/%Y", "W": "Tuần %d/%m", "M": "%m/%Y"}[freq]
    g["label"] = g["period"].dt.strftime(fmt)
    return g.reset_index(drop=True)


def monthly_series(data: FinanceData, start_month: str, end_month: str, today: date) -> pd.DataFrame:
    rows, m = [], start_month
    while m <= end_month:
        ms, me = month_start(m), month_end(m)
        income = _sum(income_events(data.incomes, ms, min(me, today)))
        led = build_ledger(data, ms, me, today)
        by_src = led.groupby("source")["amount"].sum() if len(led) else pd.Series(dtype=float)
        spend = float(led["amount"].sum()) if len(led) else 0.0
        rows.append({
            "month": m, "income": income, "spend": spend,
            "transactions": float(by_src.get("Giao dịch", 0.0)),
            "fixed": float(by_src.get("Chi phí cố định", 0.0)),
            "bnpl_paid": float(by_src.get("BNPL – trả trước", 0.0) + by_src.get("BNPL – trả góp", 0.0)),
            "net": income - spend,
        })
        m = add_months(m, 1)
    return pd.DataFrame(rows)
