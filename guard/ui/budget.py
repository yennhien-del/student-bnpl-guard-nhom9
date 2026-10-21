"""Trang Quản lý ngân sách: thu nhập, chi phí cố định, ngân sách danh mục."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from guard import db, finance as fin
from guard.ui import common as C


def render(ctx: C.Ctx) -> None:
    C.hero("Quản lý ngân sách", "Nguồn thu, chi phí cố định hằng tháng và ngân sách theo danh mục")
    t1, t2, t3 = st.tabs(["💵 Thu nhập", "🏠 Chi phí cố định", "🎯 Ngân sách danh mục"])
    with t1:
        _incomes(ctx)
    with t2:
        _fixed(ctx)
    with t3:
        _budgets(ctx)


def _incomes(ctx):
    df = ctx.data.incomes.sort_values("date", ascending=False)
    if df.empty:
        st.info("Chưa có nguồn thu nhập. Thêm nguồn thu bên dưới (đánh dấu «lặp lại hằng tháng» cho sinh hoạt phí/lương).")
    else:
        C.show_df(pd.DataFrame({
            "Tên": df["name"], "Số tiền": [fin.fmt_vnd(x) for x in df["amount"]],
            "Ngày nhận / bắt đầu": [fin.fmt_date(x) for x in df["date"]],
            "Lặp lại": ["Hằng tháng" if r else "Một lần" for r in df["recurring"]], "Ghi chú": df["note"]}))
    row = C.pick_row(df, "Chọn nguồn thu để sửa hoặc xóa", "sel_income",
                     lambda r: f"{r['name']} · {fin.fmt_vnd(r['amount'])} · {fin.fmt_date(r['date'])}")
    rid = None if row is None else int(row["id"])
    k = f"inc_{rid}_"
    with st.form(f"form_income_{rid}"):
        name = st.text_input("Tên nguồn thu", value=row["name"] if row else "", key=k + "n")
        amount = C.vnd_input("Số tiền (VNĐ)", k + "a", row["amount"] if row else 0)
        dt = C.date_input("Ngày nhận (hoặc ngày bắt đầu nếu lặp lại)", row["date"] if row else ctx.today, key=k + "d")
        rec = st.checkbox("Lặp lại hằng tháng (cùng ngày mỗi tháng)", value=bool(row["recurring"]) if row else False, key=k + "r")
        note = st.text_input("Ghi chú", value=row["note"] or "" if row else "", key=k + "o")
        ok = st.form_submit_button("💾 Lưu", type="primary")
    if ok:
        C.run_save(db.save_income, ctx.conn, rid, name, amount, dt, rec, note,
                   ok="Đã lưu nguồn thu.")
    if row is not None:
        C.delete_controls("incomes", rid, "sel_income", "nguồn thu này")


def _fixed(ctx):
    df = ctx.data.fixed_costs
    if df.empty:
        st.info("Chưa có chi phí cố định (tiền trọ, internet, học phí…).")
    else:
        C.show_df(pd.DataFrame({
            "Tên": df["name"], "Số tiền": [fin.fmt_vnd(x) for x in df["amount"]], "Danh mục": df["category"],
            "Ngày trả hằng tháng": df["due_day"], "Áp dụng từ": [fin.fmt_month(x) if x else "—" for x in df["start_month"]],
            "Trạng thái": ["Đang áp dụng" if a else "Tạm dừng" for a in df["active"]]}))
        total = float(df[df["active"] == 1]["amount"].sum())
        st.caption(f"Tổng chi phí cố định đang áp dụng: **{fin.fmt_vnd(total)}** / tháng. "
                   "Khoản đến hạn sẽ tự được tính là đã chi vào ngày trả; không cần nhập lại ở mục Chi tiêu.")
    row = C.pick_row(df, "Chọn chi phí để sửa hoặc xóa", "sel_fixed",
                     lambda r: f"{r['name']} · {fin.fmt_vnd(r['amount'])} · ngày {r['due_day']}")
    rid = None if row is None else int(row["id"])
    k = f"fix_{rid}_"
    with st.form(f"form_fixed_{rid}"):
        name = st.text_input("Tên chi phí", value=row["name"] if row else "", key=k + "n")
        amount = C.vnd_input("Số tiền mỗi tháng (VNĐ)", k + "a", row["amount"] if row else 0)
        cat = st.selectbox("Danh mục", fin.CATEGORIES, key=k + "c",
                           index=fin.CATEGORIES.index(row["category"]) if row and row["category"] in fin.CATEGORIES else 2)
        day = st.number_input("Ngày thanh toán trong tháng", 1, 31, int(row["due_day"]) if row else 5, key=k + "d")
        start = C.date_input("Áp dụng từ tháng", fin.month_start(row["start_month"]) if row and row["start_month"]
                             else fin.month_start(ctx.month), key=k + "s")
        active = st.checkbox("Đang áp dụng", value=bool(row["active"]) if row else True, key=k + "x")
        ok = st.form_submit_button("💾 Lưu", type="primary")
    if ok:
        C.run_save(db.save_fixed_cost, ctx.conn, rid, name, amount, cat, day, start, active,
                   ok="Đã lưu chi phí cố định.")
    if row is not None:
        C.delete_controls("fixed_costs", rid, "sel_fixed", "chi phí cố định này")


def _bar(r) -> str:
    pct = r["pct"]
    shown = min(pct, 1.0) if pct == pct else 0
    color = "#E5484D" if r["status"] == "Vượt ngân sách" else ("#E39A12" if r["status"] == "Gần hết" else "#1FA971")
    pct_txt = "∞" if pct == float("inf") else f"{pct:.0%}"
    return (f'<div class="bb"><div class="row"><b>{html.escape(r["category"])}</b>'
            f'<span>{fin.fmt_vnd(r["actual"])} / {fin.fmt_vnd(r["budget"])} · <b style="color:{color}">{pct_txt}</b> · {r["status"]}</span></div>'
            f'<div class="track"><div class="fill" style="width:{shown*100:.0f}%;background:{color}"></div></div></div>')


def _budgets(ctx):
    m = ctx.month
    st.markdown(f"**Ngân sách {fin.fmt_month(m)}** (đổi tháng ở thanh bên trái). "
                "Thực tế gồm giao dịch, chi phí cố định và tiền BNPL đã thực trả theo danh mục.")
    bu = fin.budget_usage(ctx.data, m, ctx.today)
    if bu.empty:
        st.info("Chưa có ngân sách cho tháng này.")
    else:
        for r in bu.to_dict("records"):
            st.markdown(_bar(r), unsafe_allow_html=True)
        total_b, total_a = bu["budget"].sum(), bu["actual"].sum()
        st.caption(f"Tổng ngân sách {fin.fmt_vnd(total_b)} · đã dùng {fin.fmt_vnd(total_a)} "
                   f"({(total_a / total_b if total_b else 0):.0%}). Ngưỡng «gần hết»: "
                   f"{ctx.data.settings['budget_warn_ratio']:.0%}.")
    prev = fin.add_months(m, -1)
    if st.button(f"📋 Sao chép ngân sách từ {fin.fmt_month(prev)}"):
        n = db.copy_budgets(ctx.conn, prev, m)
        C.flash("success" if n else "info", f"Đã sao chép {n} danh mục." if n else "Không có danh mục mới để sao chép.")
        st.rerun()
    b = ctx.data.budgets[ctx.data.budgets["month"] == m]
    row = C.pick_row(b, "Chọn danh mục để sửa hoặc xóa", f"sel_budget_{m}",
                     lambda r: f"{r['category']} · {fin.fmt_vnd(r['amount'])}")
    rid = None if row is None else int(row["id"])
    k = f"bud_{m}_{rid}_"
    with st.form(f"form_budget_{m}_{rid}"):
        cat = st.selectbox("Danh mục", fin.CATEGORIES, key=k + "c",
                           index=fin.CATEGORIES.index(row["category"]) if row else 0,
                           disabled=row is not None)
        amount = C.vnd_input("Ngân sách (VNĐ)", k + "a", row["amount"] if row else 0, step=50_000)
        ok = st.form_submit_button("💾 Lưu", type="primary")
    if ok:
        C.run_save(db.save_budget, ctx.conn, m, row["category"] if row else cat, amount, ok="Đã lưu ngân sách.")
    if row is not None:
        C.delete_controls("budgets", rid, f"sel_budget_{m}", "ngân sách này")
