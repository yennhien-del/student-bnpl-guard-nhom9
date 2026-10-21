"""Trang Báo cáo."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from guard import finance as fin
from guard.ui import common as C


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")  # BOM để Excel đọc đúng tiếng Việt


def render(ctx: C.Ctx) -> None:
    C.hero("Báo cáo", "Thu nhập, chi tiêu và BNPL theo thời gian và danh mục")
    d, today = ctx.data, ctx.today
    months = C.month_options(today)
    cur = fin.month_key(today)
    c1, c2 = st.columns(2)
    start = c1.selectbox("Từ tháng", months, index=months.index(fin.add_months(cur, -5)), format_func=fin.fmt_month, key="rp_start")
    end = c2.selectbox("Đến tháng", months, index=months.index(cur), format_func=fin.fmt_month, key="rp_end")
    if start > end:
        st.error("Tháng bắt đầu phải trước hoặc bằng tháng kết thúc.", icon="⛔")
        return
    if d.is_empty():
        st.info("Chưa có dữ liệu để lập báo cáo.")
        return

    ser = fin.monthly_series(d, start, end, today)
    labels = [fin.fmt_month(m) for m in ser["month"]]
    t_inc, t_sp = ser["income"].sum(), ser["spend"].sum()
    a, b, c, e = st.columns(4)
    with a:
        C.kpi("Thu nhập đã nhận", fin.fmt_vnd(t_inc), f"{len(ser)} tháng", "good")
    with b:
        C.kpi("Chi tiêu thực tế", fin.fmt_vnd(t_sp), "Gồm cả tiền BNPL đã trả", "")
    with c:
        C.kpi("Chênh lệch", fin.fmt_vnd(t_inc - t_sp), "Thu − chi", "bad" if t_inc - t_sp < 0 else "good")
    with e:
        C.kpi("Còn nợ BNPL", fin.fmt_vnd(fin.month_summary(d, cur, today)["bnpl_remaining_total"]), "Tại thời điểm hiện tại", "warn")

    st.markdown("#### Thu nhập và chi tiêu theo tháng")
    fig = go.Figure()
    fig.add_bar(x=labels, y=ser["income"], name="Thu nhập", marker_color="#22B8A5")
    fig.add_bar(x=labels, y=ser["spend"], name="Chi tiêu", marker_color="#3478F6")
    fig.add_scatter(x=labels, y=ser["net"], name="Chênh lệch", mode="lines+markers", line=dict(color="#142D4E"))
    fig.update_layout(barmode="group", yaxis_tickformat=",.0f")
    C.show_chart(C.style_fig(fig), key="rp_ts")

    led = fin.build_ledger(d, fin.month_start(start), fin.month_end(end), today)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Chi tiêu theo danh mục và tháng")
        if led.empty:
            st.info("Chưa có chi tiêu trong khoảng này.")
        else:
            led2 = led.copy()
            led2["month"] = [fin.month_key(x) for x in led2["date"]]
            pv = led2.pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0)
            fig = go.Figure()
            for i, cat in enumerate(pv.columns):
                fig.add_bar(x=[fin.fmt_month(m) for m in pv.index], y=pv[cat], name=cat, marker_color=C.PALETTE[i % len(C.PALETTE)])
            fig.update_layout(barmode="stack", yaxis_tickformat=",.0f")
            C.show_chart(C.style_fig(fig), key="rp_cat")
    with right:
        st.markdown(f"#### Ngân sách và thực tế – {fin.fmt_month(ctx.month)}")
        bu = fin.budget_usage(d, ctx.month, today)
        if bu.empty:
            st.info("Chưa có ngân sách cho tháng đang chọn.")
        else:
            fig = go.Figure()
            fig.add_bar(x=bu["category"], y=bu["budget"], name="Ngân sách", marker_color="#9AA7B8")
            fig.add_bar(x=bu["category"], y=bu["actual"], name="Thực tế", marker_color="#3478F6")
            fig.update_layout(barmode="group", yaxis_tickformat=",.0f")
            C.show_chart(C.style_fig(fig), key="rp_bud")

    st.markdown("#### Tổng hợp theo tháng")
    C.show_df(pd.DataFrame({"Tháng": labels, "Thu nhập đã nhận": [fin.fmt_vnd(x) for x in ser["income"]],
                            "Giao dịch": [fin.fmt_vnd(x) for x in ser["transactions"]],
                            "Chi phí cố định": [fin.fmt_vnd(x) for x in ser["fixed"]],
                            "BNPL đã trả": [fin.fmt_vnd(x) for x in ser["bnpl_paid"]],
                            "Tổng chi": [fin.fmt_vnd(x) for x in ser["spend"]],
                            "Chênh lệch": [fin.fmt_vnd(x) for x in ser["net"]]}))

    st.markdown("#### BNPL")
    ps = fin.purchase_summary(d)
    if ps.empty:
        st.info("Chưa có khoản BNPL.")
    else:
        g = ps.groupby("provider")[["order_value", "fee", "total_payable", "paid", "remaining"]].sum().reset_index()
        C.show_df(pd.DataFrame({"Dịch vụ": g["provider"], "Giá trị đơn": [fin.fmt_vnd(x) for x in g["order_value"]],
                                "Tổng phí": [fin.fmt_vnd(x) for x in g["fee"]],
                                "Tổng phải trả": [fin.fmt_vnd(x) for x in g["total_payable"]],
                                "Đã trả": [fin.fmt_vnd(x) for x in g["paid"]], "Còn nợ": [fin.fmt_vnd(x) for x in g["remaining"]]}))

    st.markdown("#### ⬇️ Xuất CSV")
    iv = fin.installments_view(d, today)
    exports = {
        "Tổng hợp theo tháng": ("tong_hop_thang.csv", ser.rename(columns={
            "month": "thang", "income": "thu_nhap_da_nhan", "spend": "tong_chi", "transactions": "giao_dich",
            "fixed": "chi_phi_co_dinh", "bnpl_paid": "bnpl_da_tra", "net": "chenh_lech"})),
        "Sổ chi tiêu thực tế": ("chi_tieu_thuc_te.csv", led.assign(date=[x.isoformat() for x in led["date"]]).rename(
            columns={"date": "ngay", "name": "noi_dung", "amount": "so_tien", "category": "danh_muc", "source": "nguon"})),
        "Lịch trả góp BNPL": ("lich_tra_gop_bnpl.csv", pd.DataFrame({
            "san_pham": iv["item"], "dich_vu": iv["provider"], "ky": iv["seq"], "han_tra": [x.isoformat() for x in iv["due_date"]],
            "so_tien": iv["amount"], "da_tra": iv["paid_amount"], "con_lai": iv["remaining"], "trang_thai": iv["status"]})),
        "Giao dịch": ("giao_dich.csv", d.transactions.assign(date=[x.isoformat() for x in d.transactions["date"]])),
    }
    cols = st.columns(len(exports))
    for col, (label, (fname, df)) in zip(cols, exports.items()):
        col.download_button(label, _csv(df), file_name=fname, mime="text/csv", key=f"dl_{fname}")
