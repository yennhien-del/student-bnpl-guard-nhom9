"""Trang Quản lý BNPL (nhập thủ công, không đồng bộ Shopee/SPayLater)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from guard import db, finance as fin
from guard.ui import common as C


def render(ctx: C.Ctx) -> None:
    C.hero("Quản lý mua trước trả sau (BNPL)", "Nhập thủ công khoản mua từ Shopee SPayLater hoặc dịch vụ khác và theo dõi từng kỳ trả")
    st.caption("ℹ️ Ứng dụng không kết nối trực tiếp với Shopee/SPayLater. Giá trị đơn hàng không được tính là chi tiêu; "
               "chỉ tiền trả trước và các kỳ bạn đã thanh toán mới vào chi tiêu thực tế.")
    t1, t2, t3 = st.tabs(["📅 Lịch trả góp", "🧾 Các khoản mua", "➕ Thêm / sửa khoản BNPL"])
    with t1:
        _schedule(ctx)
    with t2:
        _purchases(ctx)
    with t3:
        _purchase_form(ctx)


# ---------------------------------------------------------------------------
def _schedule(ctx: C.Ctx) -> None:
    iv = fin.installments_view(ctx.data, ctx.today)
    if iv.empty:
        st.info("Chưa có khoản BNPL nào. Thêm ở tab «Thêm / sửa khoản BNPL».")
        return
    s = fin.month_summary(ctx.data, fin.month_key(ctx.today), ctx.today)
    soon_mask = [(r > 0 and 0 <= dd <= int(ctx.data.settings["due_soon_days"]))
                 for r, dd in zip(iv["remaining"], iv["days_to_due"])]
    a, b, c = st.columns(3)
    with a:
        C.kpi("Tổng còn nợ BNPL", fin.fmt_vnd(s["bnpl_remaining_total"]), f"{s['bnpl_open_count']} kỳ chưa xong", "warn")
    with b:
        C.kpi("Sắp đến hạn", fin.fmt_vnd(iv[soon_mask]["remaining"].sum()),
              f"Trong {ctx.data.settings['due_soon_days']} ngày tới", "warn")
    with c:
        C.kpi("Quá hạn", fin.fmt_vnd(s["bnpl_overdue"]), f"{s['bnpl_overdue_count']} kỳ", "bad" if s["bnpl_overdue_count"] else "good")

    status = st.selectbox("Lọc theo trạng thái", ["Tất cả", "Chưa thanh toán xong", "Quá hạn", "Sắp đến hạn",
                                                   "Trả một phần", "Chưa đến hạn", "Đã thanh toán"], key="bn_status")
    v = iv.copy()
    if status == "Chưa thanh toán xong":
        v = v[v["remaining"] > 0]
    elif status != "Tất cả":
        v = v[v["status"] == status]
    v = v.sort_values(["due_date", "purchase_id", "seq"])
    C.show_df(pd.DataFrame({
        "Khoản mua": v["item"], "Dịch vụ": v["provider"], "Kỳ": v["seq"].astype(int),
        "Hạn trả": [fin.fmt_date(x) for x in v["due_date"]],
        "Số tiền kỳ": [fin.fmt_vnd(x) for x in v["amount"]], "Đã trả": [fin.fmt_vnd(x) for x in v["paid_amount"]],
        "Còn lại": [fin.fmt_vnd(x) for x in v["remaining"]], "Trạng thái": v["status"]}))

    st.markdown("#### 💸 Ghi nhận thanh toán")
    open_ = iv[iv["remaining"] > 0].sort_values(["due_date", "seq"])
    if open_.empty:
        st.success("Không còn kỳ nào cần thanh toán.")
    else:
        recs = {int(r["id"]): r for r in open_.to_dict("records")}
        iid = st.selectbox("Chọn kỳ thanh toán", list(recs), key="pay_sel",
                           format_func=lambda i: f"{recs[i]['item']} · kỳ {int(recs[i]['seq'])} · hạn "
                                                 f"{fin.fmt_date(recs[i]['due_date'])} · còn {fin.fmt_vnd(recs[i]['remaining'])}")
        rem = int(recs[iid]["remaining"])
        c1, c2 = st.columns(2)
        with c1:
            amt = C.vnd_input("Số tiền thanh toán đợt này (VNĐ)", f"pay_amt_{iid}_{rem}", rem, step=10_000, max_value=rem)
        with c2:
            pdate = C.date_input("Ngày thanh toán", ctx.today, key=f"pay_date_{iid}", max_value=ctx.today)
        st.caption("Có thể trả một phần; phần còn lại vẫn tiếp tục được theo dõi.")
        if st.button("✅ Ghi nhận thanh toán", type="primary", key="pay_btn"):
            C.run_save(db.record_payment, ctx.conn, iid, amt, pdate, ctx.today, ok="Đã ghi nhận thanh toán.")

    pay = ctx.data.payments
    if len(pay):
        with st.expander(f"Lịch sử thanh toán ({len(pay)})"):
            p = pay.sort_values("paid_date", ascending=False)
            C.show_df(pd.DataFrame({"Ngày": [fin.fmt_date(x) for x in p["paid_date"]], "Khoản mua": p["item"],
                                    "Kỳ": p["seq"].astype(int), "Số tiền": [fin.fmt_vnd(x) for x in p["amount"]]}))
            row = C.pick_row(p, "Chọn thanh toán để hoàn tác", "sel_pay",
                             lambda r: f"{fin.fmt_date(r['paid_date'])} · {r['item']} kỳ {int(r['seq'])} · {fin.fmt_vnd(r['amount'])}")
            if row is not None:
                C.delete_controls("bnpl_payments", int(row["id"]), "sel_pay", "khoản thanh toán này")


# ---------------------------------------------------------------------------
def _purchases(ctx: C.Ctx) -> None:
    ps = fin.purchase_summary(ctx.data)
    if ps.empty:
        st.info("Chưa có khoản mua BNPL nào.")
        return
    C.show_df(pd.DataFrame({
        "Sản phẩm": ps["item"], "Dịch vụ": ps["provider"], "Ngày mua": [fin.fmt_date(x) for x in ps["purchase_date"]],
        "Giá trị đơn": [fin.fmt_vnd(x) for x in ps["order_value"]], "Trả trước": [fin.fmt_vnd(x) for x in ps["down_payment"]],
        "Phí": [fin.fmt_vnd(x) for x in ps["fee"]], "Số kỳ": ps["num_installments"],
        "Tổng phải trả": [fin.fmt_vnd(x) for x in ps["total_payable"]], "Đã trả": [fin.fmt_vnd(x) for x in ps["paid"]],
        "Còn nợ": [fin.fmt_vnd(x) for x in ps["remaining"]]}))
    st.caption("Tổng phải trả = trả trước + (giá trị đơn − trả trước + phí). Phí được cộng một lần vào các kỳ.")


def _purchase_form(ctx: C.Ctx) -> None:
    ps = ctx.data.purchases
    row = C.pick_row(ps, "Chọn khoản BNPL để sửa hoặc xóa", "sel_bnpl",
                     lambda r: f"{r['item']} · {fin.fmt_vnd(r['order_value'])} · {fin.fmt_date(r['purchase_date'])}")
    rid = None if row is None else int(row["id"])
    has_pay = bool(rid) and bool(len(ctx.data.payments[ctx.data.payments["purchase_id"] == rid]))
    ver = st.session_state.get("bnpl_ver", 0)
    k = f"bnpl_{rid}_{ver if rid is None else 0}_"
    if has_pay:
        st.warning("Khoản này đã có thanh toán nên chỉ sửa được thông tin mô tả. "
                   "Muốn đổi số liệu, hãy hoàn tác thanh toán hoặc xóa và nhập lại.")

    c1, c2 = st.columns(2)
    with c1:
        provider = st.selectbox("Dịch vụ BNPL", fin.BNPL_PROVIDERS, key=k + "pv",
                                index=fin.BNPL_PROVIDERS.index(row["provider"]) if row and row["provider"] in fin.BNPL_PROVIDERS else 0)
        item = st.text_input("Sản phẩm / đơn hàng", value=row["item"] if row else "", key=k + "it")
        cat = st.selectbox("Danh mục", fin.CATEGORIES, key=k + "ct",
                           index=fin.CATEGORIES.index(row["category"]) if row and row["category"] in fin.CATEGORIES else fin.CATEGORIES.index("Mua sắm"))
        pdate = C.date_input("Ngày mua", row["purchase_date"] if row else ctx.today, key=k + "pd", disabled=has_pay)
    with c2:
        ov = C.vnd_input("Giá trị đơn hàng (VNĐ)", k + "ov", row["order_value"] if row else 0, step=50_000, disabled=has_pay)
        dp = C.vnd_input("Tiền trả trước (VNĐ)", k + "dp", row["down_payment"] if row else 0, step=10_000, disabled=has_pay)
        fee = C.vnd_input("Tổng phí (VNĐ)", k + "fe", row["fee"] if row else 0, step=5_000, disabled=has_pay)
        n = st.number_input("Số kỳ trả góp", 1, 36, int(row["num_installments"]) if row else 3, key=k + "n", disabled=has_pay)
    first = C.date_input("Ngày thanh toán kỳ đầu tiên",
                         row["first_due_date"] if row else fin.add_months_date(ctx.today, 1), key=k + "fd", disabled=has_pay)
    note = st.text_input("Ghi chú", value=(row["note"] or "") if row else "", key=k + "no")

    try:
        sched = fin.build_schedule(ov, dp, fee, n, first)
        total = dp + sum(s["amount"] for s in sched)
        st.markdown("**Xem trước lịch trả góp**")
        m1, m2, m3 = st.columns(3)
        m1.metric("Trả ngay hôm mua", fin.fmt_vnd(dp))
        m2.metric("Mỗi kỳ (xấp xỉ)", fin.fmt_vnd(sched[0]["amount"]))
        m3.metric("Tổng phải trả", fin.fmt_vnd(total), delta=f"+{fin.fmt_vnd(total - ov)} so với giá đơn" if total > ov else None,
                  delta_color="inverse")
        C.show_df(pd.DataFrame({"Kỳ": [s["seq"] for s in sched], "Hạn trả": [fin.fmt_date(s["due_date"]) for s in sched],
                                "Số tiền": [fin.fmt_vnd(s["amount"]) for s in sched]}))
    except ValueError as e:
        st.warning(str(e), icon="⚠️")

    if st.button("💾 Lưu khoản BNPL", type="primary", key=k + "save"):
        def _save():
            res = db.save_bnpl(ctx.conn, rid, provider, item, cat, pdate, ov, dp, fee, n, first, note)
            if rid is None:
                st.session_state["bnpl_ver"] = ver + 1
            return res
        C.run_save(_save, ok="Đã lưu khoản BNPL và tạo lịch trả góp." if rid is None else "Đã cập nhật khoản BNPL.")
    if row is not None:
        C.delete_controls("bnpl_purchases", rid, "sel_bnpl", "khoản BNPL này (cùng lịch trả và thanh toán liên quan)")
