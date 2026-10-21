from datetime import date

import pandas as pd
import pytest

from guard import finance as fin

TODAY = date(2026, 10, 21)


def make(incomes=(), fixed=(), txns=(), purchases=(), insts=(), pays=(), budgets=(), settings=None):
    base = {"opening_balance": 5_000_000, "balance_date": date(2026, 10, 1), "balance_configured": True}
    base.update(settings or {})
    return fin.FinanceData.from_frames(
        incomes=pd.DataFrame(list(incomes)), fixed_costs=pd.DataFrame(list(fixed)),
        transactions=pd.DataFrame(list(txns)), purchases=pd.DataFrame(list(purchases)),
        installments=pd.DataFrame(list(insts)), payments=pd.DataFrame(list(pays)),
        budgets=pd.DataFrame(list(budgets)), settings=base)


def income(amount=6_000_000, d=date(2026, 10, 1), rec=1, i=1):
    return {"id": i, "name": "Gia đình", "amount": amount, "date": d, "recurring": rec, "note": ""}


# ---------- lịch trả góp ----------
def test_schedule_sums_and_remainder_in_last():
    s = fin.build_schedule(1_000_000, 100_000, 31_000, 3, date(2026, 11, 10))
    assert sum(x["amount"] for x in s) == 900_000 + 31_000
    assert [x["amount"] for x in s] == [310_333, 310_333, 310_334]
    assert [x["seq"] for x in s] == [1, 2, 3]


def test_schedule_month_end_clamping():
    s = fin.build_schedule(300_000, 0, 0, 3, date(2026, 1, 31))
    assert [x["due_date"] for x in s] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


@pytest.mark.parametrize("args", [(0, 0, 0, 3), (100, 100, 0, 3), (100, 0, -1, 3), (100, 0, 0, 0), (100, -5, 0, 3)])
def test_schedule_validation(args):
    with pytest.raises(ValueError):
        fin.build_schedule(*args, date(2026, 11, 1))


def test_installment_status():
    f = fin.installment_status
    assert f(100, 100, date(2026, 10, 1), TODAY) == "Đã thanh toán"
    assert f(100, 0, date(2026, 10, 20), TODAY) == "Quá hạn"
    assert f(100, 40, date(2026, 10, 20), TODAY) == "Quá hạn"        # quá hạn ưu tiên hơn trả một phần
    assert f(100, 40, date(2026, 11, 20), TODAY) == "Trả một phần"
    assert f(100, 0, date(2026, 10, 25), TODAY) == "Sắp đến hạn"
    assert f(100, 0, date(2026, 12, 25), TODAY) == "Chưa đến hạn"


# ---------- không tính trùng ----------
def bnpl_data():
    sched = fin.build_schedule(1_000_000, 200_000, 0, 2, date(2026, 10, 10))   # 2 kỳ x 400.000
    p = {"id": 1, "provider": "SPayLater", "item": "Tai nghe", "category": "Mua sắm", "purchase_date": date(2026, 10, 2),
         "order_value": 1_000_000, "down_payment": 200_000, "fee": 0, "num_installments": 2,
         "first_due_date": date(2026, 10, 10), "note": ""}
    inst = [{"id": i + 1, "purchase_id": 1, "seq": s["seq"], "due_date": s["due_date"], "amount": s["amount"]}
            for i, s in enumerate(sched)]
    return p, inst


def test_order_value_not_counted_as_spending():
    p, inst = bnpl_data()
    d = make(purchases=[p], insts=inst)
    led = fin.build_ledger(d, date(2026, 10, 1), TODAY, TODAY)
    assert led["amount"].sum() == 200_000          # chỉ tiền trả trước, chưa có kỳ nào được trả
    assert fin.balance_as_of(d, TODAY) == 5_000_000 - 200_000


def test_partial_payment_flow():
    p, inst = bnpl_data()
    pays = [{"id": 1, "installment_id": 1, "amount": 150_000, "paid_date": date(2026, 10, 10)}]
    d = make(purchases=[p], insts=inst, pays=pays)
    i1 = d.installments[d.installments["id"] == 1].iloc[0]
    assert i1["paid_amount"] == 150_000 and i1["remaining"] == 250_000
    led = fin.build_ledger(d, date(2026, 10, 1), TODAY, TODAY)
    assert led["amount"].sum() == 200_000 + 150_000
    ps = fin.purchase_summary(d).iloc[0]
    assert ps["total_payable"] == 200_000 + 800_000 and ps["paid"] == 350_000 and ps["remaining"] == 650_000
    s = fin.month_summary(d, "2026-10", TODAY)
    assert s["bnpl_remaining_total"] == 650_000
    assert s["bnpl_overdue"] == 650_000 - 400_000 + 0 or s["bnpl_overdue"] == 250_000  # kỳ 1 quá hạn còn 250.000


def test_future_payment_not_in_actual():
    p, inst = bnpl_data()
    d = make(purchases=[p], insts=inst)
    s = fin.month_summary(d, "2026-10", TODAY)
    assert s["spend_actual"] == 200_000


# ---------- sự kiện lặp ----------
def test_recurring_income_and_fixed_events():
    inc = pd.DataFrame([income(rec=1, d=date(2026, 8, 31))])
    ev = fin.income_events(inc, date(2026, 8, 1), date(2026, 11, 30))
    assert [e[0] for e in ev] == [date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31), date(2026, 11, 30)]
    fx = fin.FinanceData.from_frames(fixed_costs=pd.DataFrame([
        {"id": 1, "name": "Trọ", "amount": 2_000_000, "category": "Nhà ở", "due_day": 31, "start_month": "2026-09", "active": 1}
    ])).fixed_costs
    ev = fin.fixed_events(fx, date(2026, 8, 1), date(2026, 10, 31))
    assert [e[0] for e in ev] == [date(2026, 9, 30), date(2026, 10, 31)]      # không phát sinh trước start_month


def test_fixed_cost_counts_only_once_due():
    fixed = [{"id": 1, "name": "Trọ", "amount": 2_000_000, "category": "Nhà ở", "due_day": 25, "start_month": "2026-10", "active": 1}]
    d = make(fixed=fixed)
    assert fin.build_ledger(d, date(2026, 10, 1), TODAY, TODAY).empty
    assert fin.month_summary(d, "2026-10", TODAY)["fixed_remaining"] == 2_000_000
    later = date(2026, 10, 26)
    assert fin.build_ledger(d, date(2026, 10, 1), later, later)["amount"].sum() == 2_000_000


# ---------- số dư & dự báo ----------
def test_balance_and_projection():
    d = make(incomes=[income()], fixed=[{"id": 1, "name": "Trọ", "amount": 2_000_000, "category": "Nhà ở",
                                         "due_day": 25, "start_month": "2026-10", "active": 1}],
             txns=[{"id": 1, "name": "Ăn", "amount": 300_000, "date": date(2026, 10, 5), "category": "Ăn uống",
                    "payment_method": "Tiền mặt", "note": ""}])
    assert fin.balance_as_of(d, TODAY) == 5_000_000 + 6_000_000 - 300_000
    p = fin.project(d, TODAY, 2)
    assert p[0].fixed == 2_000_000 and p[0].income == 0
    assert p[0].closing == 10_700_000 - 2_000_000          # chưa có lịch sử/ngân sách -> chi biến đổi = 0
    assert p[1].income == 6_000_000 and p[1].fixed == 2_000_000


def test_variable_spend_prefers_history_then_budget():
    hist = [{"id": 1, "name": "x", "amount": 1_000_000, "date": date(2026, 9, 10), "category": "Ăn uống", "payment_method": "Tiền mặt", "note": ""},
            {"id": 2, "name": "x", "amount": 3_000_000, "date": date(2026, 8, 10), "category": "Ăn uống", "payment_method": "Tiền mặt", "note": ""}]
    assert fin.variable_spend_estimate(make(txns=hist), "2026-11", TODAY) == (2_000_000, "trung bình các tháng gần nhất")
    bud = [{"id": 1, "month": "2026-10", "category": "Ăn uống", "amount": 1_500_000}]
    assert fin.variable_spend_estimate(make(budgets=bud), "2026-10", TODAY)[1] == "ngân sách đã đặt"
    assert fin.variable_spend_estimate(make(), "2026-10", TODAY) == (0.0, "chưa có dữ liệu")


# ---------- kiểm tra trước khi mua ----------
def rich():
    return make(incomes=[income(10_000_000)])


def test_cash_purchase_low_risk():
    r = fin.assess_purchase(rich(), TODAY, "Sách", 500_000, "cash")
    assert r["level"] == "low" and r["immediate"] == 500_000


def test_cash_purchase_exceeding_balance_is_high():
    d = make(incomes=[income(1_000_000)], settings={"opening_balance": 300_000})
    r = fin.assess_purchase(d, TODAY, "Laptop", 20_000_000, "cash")
    assert r["level"] == "high"
    assert any("lớn hơn số dư" in x for x in r["reasons"])


def test_bnpl_schedule_in_projection_and_obligations():
    d = rich()
    r = fin.assess_purchase(d, TODAY, "Điện thoại", 6_000_000, "bnpl", 0, 0, 3, date(2026, 11, 5))
    assert [a.bnpl_new for a in r["after"][:4]] == [0, 2_000_000, 2_000_000, 2_000_000]
    assert r["after"][0].closing == r["before"][0].closing          # chưa trả gì trong tháng này
    assert r["after"][1].closing == r["before"][1].closing - 2_000_000
    assert r["after"][3].closing == r["before"][3].closing - 6_000_000


def test_bnpl_down_payment_reduces_current_month():
    r = fin.assess_purchase(rich(), TODAY, "TV", 6_000_000, "bnpl", 1_000_000, 0, 2, date(2026, 11, 5))
    assert r["after"][0].closing == r["before"][0].closing - 1_000_000
    assert r["immediate"] == 1_000_000


def test_high_ratio_triggers_risk():
    d = make(incomes=[income(3_000_000)])
    r = fin.assess_purchase(d, TODAY, "X", 6_000_000, "bnpl", 0, 0, 2, date(2026, 11, 5))   # 3tr/kỳ = 100% thu nhập
    assert r["level"] == "high"


def test_caution_when_below_buffer_only():
    d = make(incomes=[income(3_000_000)], settings={"opening_balance": 0, "balance_date": date(2026, 10, 1)})
    # số dư hiện tại 3tr; mua BNPL 1 kỳ 2,7tr -> cuối tháng sau còn 3,3tr(thu) ... dùng ngưỡng đệm cao để kích hoạt
    d.settings["safety_buffer"] = 10_000_000
    r = fin.assess_purchase(d, TODAY, "X", 300_000, "cash")
    assert r["level"] == "caution"


def test_insufficient_data():
    d = make(settings={"balance_configured": False}, incomes=[income()])
    assert fin.assess_purchase(d, TODAY, "X", 100_000, "cash")["level"] == "insufficient"
    d2 = make()                       # không có thu nhập
    assert fin.assess_purchase(d2, TODAY, "X", 100_000, "cash")["level"] == "insufficient"


def test_assess_validation():
    with pytest.raises(ValueError):
        fin.assess_purchase(rich(), TODAY, "X", 0, "cash")
    with pytest.raises(ValueError):
        fin.assess_purchase(rich(), TODAY, "X", 100_000, "bnpl", 100_000, 0, 3, date(2026, 11, 1))


# ---------- ngân sách, cảnh báo, thống kê, định dạng ----------
def test_budget_usage_statuses_and_alerts():
    txns = [{"id": 1, "name": "a", "amount": 900_000, "date": date(2026, 10, 3), "category": "Ăn uống", "payment_method": "Tiền mặt", "note": ""},
            {"id": 2, "name": "b", "amount": 450_000, "date": date(2026, 10, 3), "category": "Đi lại", "payment_method": "Tiền mặt", "note": ""},
            {"id": 3, "name": "c", "amount": 100_000, "date": date(2026, 10, 3), "category": "Giải trí", "payment_method": "Tiền mặt", "note": ""}]
    bud = [{"id": 1, "month": "2026-10", "category": "Ăn uống", "amount": 800_000},
           {"id": 2, "month": "2026-10", "category": "Đi lại", "amount": 500_000},
           {"id": 3, "month": "2026-10", "category": "Giải trí", "amount": 500_000}]
    d = make(incomes=[income()], txns=txns, budgets=bud)
    bu = fin.budget_usage(d, "2026-10", TODAY).set_index("category")
    assert bu.loc["Ăn uống", "status"] == "Vượt ngân sách"
    assert bu.loc["Đi lại", "status"] == "Gần hết"
    assert bu.loc["Giải trí", "status"] == "Trong ngân sách"
    texts = " ".join(a["text"] for a in fin.build_alerts(d, TODAY, "2026-10"))
    assert "Vượt ngân sách «Ăn uống»" in texts and "Sắp hết ngân sách «Đi lại»" in texts


def test_overdue_and_due_soon_alerts():
    p, inst = bnpl_data()                       # kỳ 1 hạn 10/10 (quá hạn), kỳ 2 hạn 10/11
    d = make(incomes=[income()], purchases=[p], insts=inst)
    alerts = fin.build_alerts(d, TODAY, "2026-10")
    assert alerts[0]["level"] == "danger" and "Quá hạn 11 ngày" in alerts[0]["text"]


def test_aggregate_spending():
    df = pd.DataFrame({"date": [date(2026, 10, 19), date(2026, 10, 21), date(2026, 10, 26)], "amount": [10, 20, 30]})
    assert fin.aggregate_spending(df, "D")["amount"].tolist() == [10, 20, 30]
    assert fin.aggregate_spending(df, "W")["amount"].tolist() == [30, 30]      # tuần bắt đầu thứ Hai 19/10 và 26/10
    assert fin.aggregate_spending(df, "M")["amount"].tolist() == [60]
    assert fin.aggregate_spending(df.iloc[0:0], "D").empty


def test_formatting():
    assert fin.fmt_vnd(1234567) == "1.234.567 ₫"
    assert fin.fmt_vnd(-50000) == "-50.000 ₫"
    assert fin.fmt_date(date(2026, 1, 5)) == "05/01/2026"
    assert fin.fmt_month("2026-03") == "Tháng 03/2026"
    assert fin.add_months("2026-11", 3) == "2027-02" and fin.add_months("2026-01", -2) == "2025-11"
