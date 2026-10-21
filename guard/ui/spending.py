"""Trang Chi tiêu hằng ngày."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from guard import db, finance as fin
from guard.ui import common as C


def _table(df: pd.DataFrame, today) -> pd.DataFrame:
    return pd.DataFrame({
        "Ngày": [fin.fmt_date(x) for x in df["date"]], "Khoản chi": df["name"], "Danh mục": df["category"],
        "Thanh toán": df["payment_method"], "Số tiền": [fin.fmt_vnd(x) for x in df["amount"]],
        "Ghi chú": df["note"].fillna(""),
        "Trạng thái": ["Dự kiến" if x > today else "Đã phát sinh" for x in df["date"]]})


def render(ctx: C.Ctx) -> None:
    C.hero("Chi tiêu hằng ngày", "Ghi lại, tìm kiếm và thống kê các khoản chi")
    st.caption("ℹ️ Mua bằng BNPL không nhập ở đây: hãy thêm ở mục **BNPL**. Chỉ tiền thực trả "
               "(trả trước + các kỳ đã thanh toán) mới được tính vào chi tiêu, nên không bị tính trùng.")
    ms, me = fin.month_start(ctx.month), fin.month_end(ctx.month)
    f1, f2, f3 = st.columns([2, 2, 2])
    q = f1.text_input("🔍 Tìm kiếm", placeholder="Tên hoặc ghi chú…", key="sp_q")
    cats = f2.multiselect("Danh mục", fin.CATEGORIES, key="sp_cats")
    rng = f3.date_input("Khoảng ngày", value=(ms, me), format="DD/MM/YYYY", key=f"sp_range_{ctx.month}")
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        lo, hi = rng
    else:
        lo, hi = ms, me
        st.caption("Chọn đủ ngày bắt đầu và kết thúc để lọc theo khoảng.")

    df = ctx.data.transactions.copy()
    if len(df):
        df = df[C.fin._between(df["date"], lo, hi)]
        if cats:
            df = df[df["category"].isin(cats)]
        if q.strip():
            ql = q.strip().lower()
            df = df[df["name"].str.lower().str.contains(ql, regex=False)
                    | df["note"].fillna("").str.lower().str.contains(ql, regex=False)]
        df = df.sort_values(["date", "id"], ascending=False)

    tab1, tab2, tab3 = st.tabs(["📋 Danh sách", "➕ Thêm / sửa / xóa", "📈 Thống kê"])
    with tab1:
        a, b = st.columns(2)
        with a:
            C.kpi("Tổng chi (đã lọc)", fin.fmt_vnd(df[[d <= ctx.today for d in df["date"]]]["amount"].sum() if len(df) else 0),
                  f"{len(df)} giao dịch", "")
        if df.empty:
            st.info("Không có giao dịch nào khớp bộ lọc.")
        else:
            C.show_df(_table(df, ctx.today))
    with tab2:
        _form(ctx, df)
    with tab3:
        _stats(ctx, df)


def _form(ctx, df):
    sub = df.head(300)
    row = C.pick_row(sub, "Chọn giao dịch để sửa hoặc xóa (trong danh sách đã lọc)", "sel_txn",
                     lambda r: f"{fin.fmt_date(r['date'])} · {r['name']} · {fin.fmt_vnd(r['amount'])}")
    rid = None if row is None else int(row["id"])
    k = f"txn_{rid}_"
    with st.form(f"form_txn_{rid}", clear_on_submit=row is None):
        name = st.text_input("Tên khoản chi", value=row["name"] if row else "", key=k + "n")
        c1, c2 = st.columns(2)
        with c1:
            amount = C.vnd_input("Số tiền (VNĐ)", k + "a", row["amount"] if row else 0, step=5_000)
            cat = st.selectbox("Danh mục", fin.CATEGORIES, key=k + "c",
                               index=fin.CATEGORIES.index(row["category"]) if row and row["category"] in fin.CATEGORIES else 0)
        with c2:
            dt = C.date_input("Ngày", row["date"] if row else ctx.today, key=k + "d")
            pm = st.selectbox("Phương thức thanh toán", fin.PAYMENT_METHODS, key=k + "p",
                              index=fin.PAYMENT_METHODS.index(row["payment_method"]) if row and row["payment_method"] in fin.PAYMENT_METHODS else 0)
        note = st.text_input("Ghi chú", value=(row["note"] or "") if row else "", key=k + "o")
        ok = st.form_submit_button("💾 Lưu", type="primary")
    if ok:
        C.run_save(db.save_transaction, ctx.conn, rid, name, amount, dt, cat, pm, note,
                   ok="Đã lưu giao dịch.")
    if row is not None:
        C.delete_controls("transactions", rid, "sel_txn", "giao dịch này")


def _stats(ctx, df):
    actual = df[[d <= ctx.today for d in df["date"]]] if len(df) else df
    if actual.empty:
        st.info("Chưa có dữ liệu để thống kê trong bộ lọc hiện tại.")
        return
    days = max(1, (max(actual["date"]) - min(actual["date"])).days + 1)
    total = float(actual["amount"].sum())
    a, b, c = st.columns(3)
    with a:
        C.kpi("Tổng chi", fin.fmt_vnd(total), "Giao dịch đã phát sinh", "")
    with b:
        C.kpi("Trung bình mỗi ngày", fin.fmt_vnd(total / days), f"Trong {days} ngày", "")
    with c:
        C.kpi("Số giao dịch", str(len(actual)), "", "")
    freq = st.radio("Thống kê theo", ["Ngày", "Tuần", "Tháng"], horizontal=True, key="sp_freq")
    agg = fin.aggregate_spending(actual, {"Ngày": "D", "Tuần": "W", "Tháng": "M"}[freq])
    fig = go.Figure(go.Bar(x=agg["label"], y=agg["amount"], marker_color="#3478F6",
                           hovertemplate="%{x}: %{y:,.0f} ₫<extra></extra>"))
    fig.update_layout(yaxis_tickformat=",.0f", title=f"Chi tiêu theo {freq.lower()}")
    fig.update_xaxes(type="category")
    C.show_chart(C.style_fig(fig), key="sp_chart")
    by = actual.groupby("category")["amount"].sum().sort_values(ascending=False).reset_index()
    by["Tỷ trọng"] = [f"{v / total:.0%}" for v in by["amount"]]
    by["amount"] = [fin.fmt_vnd(v) for v in by["amount"]]
    C.show_df(by.rename(columns={"category": "Danh mục", "amount": "Số tiền"}))
