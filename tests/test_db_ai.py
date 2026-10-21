from datetime import date, timedelta

import pytest

from guard import ai, db, finance as fin, seed

TODAY = date(2026, 10, 21)


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    yield c
    c.close()


def test_persistence_across_connections(tmp_path):
    path = tmp_path / "p.db"
    c1 = db.connect(path); db.init_db(c1)
    db.save_transaction(c1, None, "Cà phê", 35_000, TODAY, "Ăn uống", "Tiền mặt")
    c1.close()
    c2 = db.connect(path)
    assert len(db.load_data(c2).transactions) == 1
    c2.close()


@pytest.mark.parametrize("kwargs", [
    dict(name="", amount=1000), dict(name="x", amount=0), dict(name="x", amount=-5), dict(name="x", amount="abc"),
])
def test_transaction_validation(conn, kwargs):
    with pytest.raises(ValueError):
        db.save_transaction(conn, None, kwargs["name"], kwargs["amount"], TODAY, "Ăn uống", "Tiền mặt")


def test_invalid_category_and_method(conn):
    with pytest.raises(ValueError):
        db.save_transaction(conn, None, "x", 1000, TODAY, "Không có", "Tiền mặt")
    with pytest.raises(ValueError):
        db.save_transaction(conn, None, "x", 1000, TODAY, "Ăn uống", "BNPL")      # BNPL không nhập ở giao dịch


def test_update_and_delete_transaction(conn):
    rid = db.save_transaction(conn, None, "A", 1000, TODAY, "Ăn uống", "Tiền mặt")
    db.save_transaction(conn, rid, "B", 2000, TODAY, "Đi lại", "Ví điện tử", "ghi chú")
    row = db.load_data(conn).transactions.iloc[0]
    assert row["name"] == "B" and row["amount"] == 2000 and row["category"] == "Đi lại"
    db.delete_row(conn, "transactions", rid)
    assert db.load_data(conn).transactions.empty
    with pytest.raises(ValueError):
        db.delete_row(conn, "transactions", rid)


def create_bnpl(conn, n=3, down=0, fee=30_000):
    db.save_bnpl(conn, None, "SPayLater", "Giày", "Mua sắm", TODAY - timedelta(days=3), 900_000, down, fee, n,
                 TODAY + timedelta(days=7))
    return db.load_data(conn)


def test_bnpl_creates_schedule_and_payment_limits(conn):
    d = create_bnpl(conn)
    assert len(d.installments) == 3 and d.installments["amount"].sum() == 930_000
    iid = int(d.installments.iloc[0]["id"])
    db.record_payment(conn, iid, 100_000, TODAY, TODAY)
    with pytest.raises(ValueError):                         # vượt phần còn nợ
        db.record_payment(conn, iid, 250_000, TODAY, TODAY)
    with pytest.raises(ValueError):                         # ngày ở tương lai
        db.record_payment(conn, iid, 10_000, TODAY + timedelta(days=1), TODAY)
    db.record_payment(conn, iid, 210_000, TODAY, TODAY)     # trả nốt kỳ 1 (310.000)
    with pytest.raises(ValueError):                         # đã trả đủ
        db.record_payment(conn, iid, 1_000, TODAY, TODAY)
    d = db.load_data(conn)
    assert d.installments.iloc[0]["remaining"] == 0


def test_bnpl_edit_locked_after_payment_and_cascade_delete(conn):
    d = create_bnpl(conn)
    pid = int(d.purchases.iloc[0]["id"])
    db.record_payment(conn, int(d.installments.iloc[0]["id"]), 50_000, TODAY, TODAY)
    res = db.save_bnpl(conn, pid, "SPayLater", "Giày mới", "Mua sắm", TODAY, 5_000_000, 0, 0, 2, TODAY + timedelta(days=30))
    assert res == "info_only"
    d = db.load_data(conn)
    assert d.purchases.iloc[0]["item"] == "Giày mới" and d.purchases.iloc[0]["order_value"] == 900_000
    assert len(d.installments) == 3
    db.delete_row(conn, "bnpl_purchases", pid)
    d = db.load_data(conn)
    assert d.installments.empty and d.payments.empty


def test_bnpl_regenerates_schedule_when_no_payments(conn):
    d = create_bnpl(conn)
    pid = int(d.purchases.iloc[0]["id"])
    assert db.save_bnpl(conn, pid, "SPayLater", "Giày", "Mua sắm", TODAY, 900_000, 0, 0, 2, TODAY + timedelta(days=5)) == "updated"
    assert len(db.load_data(conn).installments) == 2


def test_bnpl_validation(conn):
    with pytest.raises(ValueError):
        db.save_bnpl(conn, None, "X", "Y", "Mua sắm", TODAY, 100_000, 100_000, 0, 2, TODAY)      # trả trước >= giá
    with pytest.raises(ValueError):
        db.save_bnpl(conn, None, "X", "Y", "Mua sắm", TODAY, 100_000, 0, 0, 2, TODAY - timedelta(days=1))


def test_settings_validation_and_roundtrip(conn):
    db.set_opening_balance(conn, 1_500_000, date(2026, 10, 1))
    s = db.get_settings(conn)
    assert s["opening_balance"] == 1_500_000 and s["balance_configured"] and s["balance_date"] == date(2026, 10, 1)
    with pytest.raises(ValueError):
        db.set_settings(conn, caution_ratio=0.9, high_ratio=0.5)


def test_budget_upsert_and_copy(conn):
    db.save_budget(conn, "2026-09", "Ăn uống", 1_000_000)
    db.save_budget(conn, "2026-09", "Ăn uống", 1_200_000)
    assert db.copy_budgets(conn, "2026-09", "2026-10") == 1
    assert db.copy_budgets(conn, "2026-09", "2026-10") == 0
    b = db.load_data(conn).budgets
    assert len(b) == 2 and set(b["amount"]) == {1_200_000}


def test_seed_demo_runs_and_features_work(conn):
    assert seed.seed_demo(conn, TODAY, force=True)
    assert seed.seed_demo(conn, TODAY) is False        # không ghi đè khi đã có dữ liệu
    d = db.load_data(conn)
    m = fin.month_key(TODAY)
    fin.month_summary(d, m, TODAY)
    fin.budget_usage(d, m, TODAY)
    fin.build_alerts(d, TODAY, m)
    r = fin.assess_purchase(d, TODAY, "Laptop", 10_000_000, "bnpl", 1_000_000, 100_000, 6, TODAY + timedelta(days=30))
    assert r["level"] in fin.RISK_LABELS


# ---------- AI ----------
def test_ai_not_configured(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(ai, "_secret", lambda n: None)
    assert not ai.is_configured()
    with pytest.raises(ai.AIError, match="chưa được cấu hình"):
        ai.ask([{"role": "user", "content": "hi"}], {})


def test_placeholder_key_is_not_configured(monkeypatch):
    monkeypatch.setattr(ai, "_secret", lambda n: "your_key_here" if "KEY" in n else None)
    assert not ai.is_configured()


def test_ai_context_uses_python_numbers_and_request_shape(conn, monkeypatch):
    seed.seed_demo(conn, TODAY, force=True)
    d = db.load_data(conn)
    ctx = ai.build_context(d, fin.month_key(TODAY), TODAY)
    assert ctx["so_du_hien_tai"] == round(fin.balance_as_of(d, TODAY))
    assert ctx["tong_quan_thang"]["chi_tieu_thuc_te"] == round(fin.month_summary(d, "2026-10", TODAY)["spend_actual"])

    captured = {}

    class R:
        status_code = 200
        def json(self): return {"content": [{"type": "text", "text": "Xin chào"}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, body=json)
        return R()

    monkeypatch.setattr(ai, "_secret", lambda n: "sk-real-key" if n == "ANTHROPIC_API_KEY" else None)
    monkeypatch.setattr(ai.requests, "post", fake_post)
    assert ai.ask([{"role": "user", "content": "Tóm tắt giúp mình"}], ctx) == "Xin chào"
    assert captured["headers"]["x-api-key"] == "sk-real-key"
    assert "không bịa số liệu" in captured["body"]["system"].lower() or "không bịa" in captured["body"]["system"]
    assert str(ctx["so_du_hien_tai"]) in captured["body"]["system"]


def test_ai_http_errors(monkeypatch):
    monkeypatch.setattr(ai, "_secret", lambda n: "sk-real" if n == "ANTHROPIC_API_KEY" else None)

    class R:
        def __init__(self, c): self.status_code = c; self.text = "x"
        def json(self): return {"error": {"message": "boom"}}

    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: R(401))
    with pytest.raises(ai.AIError, match="API key"):
        ai.ask([{"role": "user", "content": "hi"}], {})
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: R(500))
    with pytest.raises(ai.AIError, match="500"):
        ai.ask([{"role": "user", "content": "hi"}], {})
