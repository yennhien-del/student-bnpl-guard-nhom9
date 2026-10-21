"""Trang Kiểm tra trước khi mua."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from guard import db, finance as fin
from guard.ui import common as C

CASH = "Trả ngay (tiền mặt / chuyển khoản)"
BNPL = "BNPL – trả góp"


def _to_ai() -> None:
    st.session_state["nav"] = "🤖 Guard AI"
    st.session_state["_pending_prompt"] = ("Hãy phân tích tác động của khoản mua vừa kiểm tra lên tài chính của tôi "
                                           "và cho biết nên làm gì.")


def render(ctx: C.Ctx) -> None:
    C.hero("Kiểm tra trước khi mua", "Xem tác động lên dòng tiền các tháng tới trước khi quyết định")
    c1, c2 = st.columns(2)
    with c1:
        item = st.text_input("Sản phẩm dự kiến mua", placeholder="VD: Laptop học tập", key="ck_item")
        value = C.vnd_input("Giá trị đơn hàng (VNĐ)", "ck_value", 0, step=100_000)
        plan = st.radio("Phương án thanh toán", [CASH, BNPL], key="ck_plan")
    down = fee = 0
    n, first, provider, cat = 3, fin.add_months_date(ctx.today, 1), fin.BNPL_PROVIDERS[0], "Mua sắm"
    with c2:
        if plan == BNPL:
            down = C.vnd_input("Tiền trả trước (VNĐ)", "ck_down", 0, step=50_000)
            fee = C.vnd_input("Tổng phí (VNĐ)", "ck_fee", 0, step=5_000)
            n = st.number_input("Số kỳ trả góp", 1, 36, 3, key="ck_n")
            first = C.date_input("Ngày thanh toán kỳ đầu", fin.add_months_date(ctx.today, 1), key="ck_first")
            provider = st.selectbox("Dịch vụ BNPL", fin.BNPL_PROVIDERS, key="ck_provider")
            cat = st.selectbox("Danh mục", fin.CATEGORIES, index=fin.CATEGORIES.index("Mua sắm"), key="ck_cat")
        else:
            st.info("Số tiền sẽ được trừ ngay khỏi số dư hiện tại.")

    if st.button("🔎 Kiểm tra", type="primary", key="ck_run"):
        try:
            res = fin.assess_purchase(ctx.data, ctx.today, item, value, "bnpl" if plan == BNPL else "cash",
                                      down, fee, n, first)
            res["inputs"].update({"provider": provider, "category": cat})
            st.session_state["check_result"] = res
        except ValueError as e:
            st.session_state.pop("check_result", None)
            st.error(str(e), icon="⛔")

    res = st.session_state.get("check_result")
    if not res:
        st.caption("Nhập thông tin rồi bấm «Kiểm tra». Kết quả dựa trên dữ liệu thu nhập, chi phí cố định, BNPL và chi tiêu bạn đã nhập.")
        return
    _result(ctx, res)


def _result(ctx: C.Ctx, res: dict) -> None:
    st.markdown("---")
    st.markdown(f"### Kết quả cho: {res['item']}")
    st.markdown(f'<span class="badge {res["level"]}">{res["label"]}</span>', unsafe_allow_html=True)
    for r in res["reasons"]:
        st.markdown(f"- {r}")

    after_now = res["after"][0]
    a, b, c, d = st.columns(4)
    a.metric("Số dư hiện tại", fin.fmt_vnd(res["current_balance"]))
    b.metric("Trả ngay", fin.fmt_vnd(res["immediate"]))
    c.metric("Tổng các kỳ mới", fin.fmt_vnd(sum(s["amount"] for s in res["schedule"])))
    d.metric("Số dư dự kiến cuối tháng sau khi mua", fin.fmt_vnd(after_now.closing),
             delta=fin.fmt_vnd(after_now.closing - res["before"][0].closing), delta_color="normal")

    rows = []
    for b_, a_ in zip(res["before"], res["after"]):
        rows.append({"Tháng": fin.fmt_month(a_.month), "Chi phí cố định": fin.fmt_vnd(a_.fixed_full),
                     "BNPL hiện có": fin.fmt_vnd(a_.bnpl_existing), "Khoản mới": fin.fmt_vnd(a_.bnpl_new),
                     "Tổng nghĩa vụ": fin.fmt_vnd(a_.obligations),
                     "Tỷ lệ/thu nhập": f"{a_.ratio:.0%}" if a_.ratio is not None else "—",
                     "Số dư dự kiến TRƯỚC khi mua": fin.fmt_vnd(b_.closing),
                     "Số dư dự kiến SAU khi mua": fin.fmt_vnd(a_.closing)})
    C.show_df(pd.DataFrame(rows))

    fig = go.Figure()
    x = [fin.fmt_month(p.month) for p in res["after"]]
    fig.add_scatter(x=x, y=[p.closing for p in res["before"]], name="Trước khi mua", mode="lines+markers",
                    line=dict(color="#9AA7B8"))
    fig.add_scatter(x=x, y=[p.closing for p in res["after"]], name="Sau khi mua", mode="lines+markers",
                    line=dict(color="#3478F6", width=3))
    fig.add_hline(y=0, line_dash="dot", line_color="#E5484D")
    fig.update_layout(title="Số dư dự kiến cuối tháng", yaxis_tickformat=",.0f")
    C.show_chart(C.style_fig(fig), key="ck_chart")

    for n_ in res["notes"]:
        st.caption("• " + n_)
    s = ctx.data.settings
    st.caption(f"Quy tắc tính (do Python, minh bạch): «rủi ro cao» nếu phải trả ngay nhiều hơn số dư, số dư dự kiến âm hoặc "
               f"nghĩa vụ cố định + BNPL > {s['high_ratio']:.0%} thu nhập; «cần cân nhắc» nếu số dư thấp hơn mức đệm "
               f"{fin.fmt_vnd(s['safety_buffer'])} hoặc nghĩa vụ > {s['caution_ratio']:.0%} thu nhập. Đây là ngưỡng tự thiết lập "
               f"(chỉnh được ở Cài đặt), **không phải chuẩn tài chính chính thức** và không thay thế tư vấn chuyên môn.")

    b1, b2 = st.columns(2)
    b1.button("🤖 Hỏi Guard AI về khoản mua này", on_click=_to_ai)
    if res["mode"] == "bnpl" and b2.button("➕ Ghi nhận vào danh sách BNPL"):
        i = res["inputs"]
        C.run_save(db.save_bnpl, ctx.conn, None, i.get("provider", fin.BNPL_PROVIDERS[0]), res["item"],
                   i.get("category", "Mua sắm"), ctx.today, res["order_value"], i["down_payment"], i["fee"], i["n"],
                   i["first_due"], "Tạo từ mục Kiểm tra trước khi mua", ok="Đã thêm vào danh sách BNPL.")
