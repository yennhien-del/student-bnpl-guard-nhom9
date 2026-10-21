"""Trang Cài đặt."""
from __future__ import annotations

import streamlit as st

from guard import ai, db, finance as fin, seed
from guard.ui import common as C


def render(ctx: C.Ctx) -> None:
    C.hero("Cài đặt", "Số dư ban đầu, ngưỡng cảnh báo, AI và dữ liệu")
    s = ctx.data.settings

    st.markdown("#### 💼 Số dư ban đầu")
    st.caption("Số dư hiện tại = số dư ban đầu + thu nhập đã nhận − chi tiêu thực tế kể từ ngày áp dụng. "
               "Chỉ các khoản từ ngày này trở đi được tính.")
    with st.form("form_balance"):
        bal = st.number_input("Số dư tại ngày áp dụng (VNĐ, có thể âm)", value=int(s["opening_balance"]), step=100_000)
        dt = C.date_input("Ngày áp dụng", s["balance_date"] or fin.month_start(ctx.month), key="set_bal_date")
        if st.form_submit_button("💾 Lưu số dư", type="primary"):
            C.run_save(db.set_opening_balance, ctx.conn, bal, dt, ok="Đã lưu số dư ban đầu.")
    if not s["balance_configured"]:
        st.warning("Bạn chưa thiết lập số dư ban đầu nên mức rủi ro sẽ hiển thị «Chưa đủ dữ liệu».")

    st.markdown("#### ⚖️ Ngưỡng đánh giá rủi ro (tự thiết lập)")
    st.caption("Các ngưỡng này do bạn tùy chỉnh, **không phải chuẩn tài chính chính thức**.")
    with st.form("form_thresholds"):
        c1, c2 = st.columns(2)
        buf = c1.number_input("Mức đệm an toàn tối thiểu (VNĐ)", min_value=0, value=int(s["safety_buffer"]), step=100_000)
        due = c2.number_input("Cảnh báo BNPL trước hạn (ngày)", 1, 60, int(s["due_soon_days"]))
        caution = c1.slider("Ngưỡng «cần cân nhắc»: (cố định + BNPL) / thu nhập", 0.1, 1.0, float(s["caution_ratio"]), 0.05)
        high = c2.slider("Ngưỡng «rủi ro cao»", 0.2, 1.5, float(s["high_ratio"]), 0.05)
        warn = st.slider("Cảnh báo ngân sách «gần hết» khi dùng từ", 0.5, 1.0, float(s["budget_warn_ratio"]), 0.05)
        if st.form_submit_button("💾 Lưu ngưỡng", type="primary"):
            C.run_save(db.set_settings, ctx.conn, safety_buffer=int(buf), due_soon_days=int(due), caution_ratio=caution,
                       high_ratio=high, budget_warn_ratio=warn, ok="Đã lưu ngưỡng.")

    st.markdown("#### 🤖 Guard AI")
    cfg = ai.get_config()
    if cfg["api_key"]:
        st.success(f"Đã cấu hình ({cfg['provider']}, mô hình {cfg['model']}). API key được đọc từ biến môi trường/Secrets.")
    else:
        st.warning(f"Chưa cấu hình. Đặt `{cfg['key_name']}` trong file `.env` hoặc Streamlit Secrets rồi khởi động lại (xem README).")

    st.markdown("#### 🗂️ Dữ liệu")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Nạp dữ liệu demo** (xóa toàn bộ dữ liệu hiện có)")
        ok1 = st.checkbox("Tôi hiểu dữ liệu hiện tại sẽ bị thay thế", key="seed_ok")
        if st.button("✨ Nạp dữ liệu demo", disabled=not ok1):
            seed.seed_demo(ctx.conn, ctx.today, force=True)
            st.session_state.pop("check_result", None)
            C.flash("success", "Đã nạp dữ liệu demo.")
            st.rerun()
    with c2:
        st.markdown("**Xóa toàn bộ dữ liệu**")
        ok2 = st.checkbox("Tôi muốn xóa vĩnh viễn mọi dữ liệu", key="wipe_ok")
        if st.button("🗑️ Xóa tất cả", disabled=not ok2):
            db.clear_all(ctx.conn)
            st.session_state.pop("check_result", None)
            st.session_state["skip_welcome"] = True
            C.flash("success", "Đã xóa toàn bộ dữ liệu.")
            st.rerun()
    st.caption("Dữ liệu được lưu trong SQLite (data/guard.db) và vẫn còn sau khi khởi động lại.")
