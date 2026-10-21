"""Trang Tổng quan."""
from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st

from guard import finance as fin, seed
from guard.ui import common as C


def _welcome(ctx: C.Ctx) -> None:
    st.markdown('<div class="card"><h3>👋 Chào mừng đến với Student BNPL Guard</h3>'
                '<p>Chưa có dữ liệu nào. Bạn có thể xem thử ngay với dữ liệu demo, '
                'hoặc bắt đầu với dữ liệu trống và tự nhập (nhớ đặt số dư ban đầu trong Cài đặt).</p></div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("✨ Nạp dữ liệu demo", type="primary"):
        seed.seed_demo(ctx.conn, ctx.today, force=True)
        C.flash("success", "Đã nạp dữ liệu demo.")
        st.rerun()
    if c2.button("📝 Bắt đầu với dữ liệu trống"):
        st.session_state["skip_welcome"] = True
        st.rerun()


def render(ctx: C.Ctx) -> None:
    d, today, m = ctx.data, ctx.today, ctx.month
    C.hero("Tổng quan tài chính", f"{fin.fmt_month(m)} · hôm nay {fin.fmt_date(today)}")
    if d.is_empty() and not st.session_state.get("skip_welcome"):
        _welcome(ctx)
        return

    s = fin.month_summary(d, m, today)
    cur = fin.month_key(today)
    bal = fin.balance_as_of(d, today)
    if m >= cur:
        idx = len(fin.months_between(today, fin.month_start(m))) - 1
        proj = fin.project(d, today, idx + 1)[-1]
        est, est_label = proj.closing, "Số dư dự kiến cuối tháng"
        est_sub = f"Đã trừ chi tiêu biến đổi ước tính {fin.fmt_vnd(proj.variable)}"
    else:
        est, est_label = fin.balance_as_of(d, fin.month_end(m)), "Số dư cuối tháng (thực tế)"
        est_sub = "Tháng đã qua, số liệu thực tế"

    c1, c2, c3 = st.columns(3)
    with c1:
        C.kpi("Tổng thu nhập tháng", fin.fmt_vnd(s["income_total"]),
              f"Đã nhận {fin.fmt_vnd(s['income_received'])}", "good")
    with c2:
        C.kpi("Chi tiêu thực tế", fin.fmt_vnd(s["spend_actual"]),
              "Giao dịch + chi phí cố định + tiền BNPL đã trả", "")
    with c3:
        C.kpi("Số dư hiện tại", fin.fmt_vnd(bal), "Tính đến hôm nay", "bad" if bal < 0 else "navy")
    c4, c5, c6 = st.columns(3)
    with c4:
        C.kpi("Nghĩa vụ BNPL còn lại", fin.fmt_vnd(s["bnpl_remaining_total"]),
              f"{s['bnpl_open_count']} kỳ chưa thanh toán xong", "warn" if s["bnpl_remaining_total"] else "")
    with c5:
        tone = "bad" if s["bnpl_overdue_count"] else ("warn" if s["bnpl_due_month"] else "")
        C.kpi("BNPL đến hạn trong tháng", fin.fmt_vnd(s["bnpl_due_month"]),
              f"Quá hạn: {fin.fmt_vnd(s['bnpl_overdue'])} ({s['bnpl_overdue_count']} kỳ)", tone)
    with c6:
        C.kpi(est_label, fin.fmt_vnd(est), est_sub, "bad" if est < 0 else "good")

    st.markdown("#### 🔔 Cảnh báo tài chính")
    for a in fin.build_alerts(d, today, m)[:6]:
        C.alert(a["level"], a["text"])

    left, right = st.columns(2)
    with left:
        st.markdown("#### Cơ cấu chi tiêu")
        by_cat = s["spend_by_category"]
        if len(by_cat) == 0:
            st.info("Chưa có chi tiêu thực tế trong tháng này.")
        else:
            fig = go.Figure(go.Pie(labels=list(by_cat.index), values=list(by_cat.values), hole=0.55,
                                   marker=dict(colors=C.PALETTE), textinfo="percent",
                                   hovertemplate="%{label}: %{value:,.0f} ₫<extra></extra>"))
            C.show_chart(C.style_fig(fig), key="dash_pie")
    with right:
        st.markdown("#### Ngân sách và chi tiêu thực tế")
        bu = fin.budget_usage(d, m, today)
        if bu.empty:
            st.info("Chưa thiết lập ngân sách cho tháng này (vào mục Ngân sách).")
        else:
            fig = go.Figure()
            fig.add_bar(x=bu["category"], y=bu["budget"], name="Ngân sách", marker_color="#9AA7B8")
            fig.add_bar(x=bu["category"], y=bu["actual"], name="Thực tế", marker_color="#3478F6")
            fig.update_layout(barmode="group", yaxis_tickformat=",.0f")
            C.show_chart(C.style_fig(fig), key="dash_budget")

    l2, r2 = st.columns(2)
    with l2:
        st.markdown("#### Giao dịch gần đây")
        led = fin.build_ledger(d, today - timedelta(days=90), today, today).head(10)
        if led.empty:
            st.info("Chưa có giao dịch.")
        else:
            C.show_df(_ledger_table(led))
    with r2:
        st.markdown("#### Kỳ BNPL sắp tới")
        iv = fin.installments_view(d, today)
        up = iv[iv["remaining"] > 0].sort_values("due_date").head(6)
        if up.empty:
            st.success("Không còn kỳ BNPL nào cần thanh toán.")
        else:
            C.show_df(_inst_table(up))


def _ledger_table(led):
    import pandas as pd
    return pd.DataFrame({"Ngày": [fin.fmt_date(x) for x in led["date"]], "Nội dung": led["name"],
                         "Danh mục": led["category"], "Nguồn": led["source"],
                         "Số tiền": [fin.fmt_vnd(x) for x in led["amount"]]})


def _inst_table(df):
    import pandas as pd
    return pd.DataFrame({"Khoản mua": df["item"], "Kỳ": df["seq"].astype(int),
                         "Hạn trả": [fin.fmt_date(x) for x in df["due_date"]],
                         "Còn lại": [fin.fmt_vnd(x) for x in df["remaining"]],
                         "Trạng thái": df["status"]})
