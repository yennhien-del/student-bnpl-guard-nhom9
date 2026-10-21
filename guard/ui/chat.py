"""Trang Guard AI."""
from __future__ import annotations

import streamlit as st

from guard import ai, finance as fin
from guard.ui import common as C

QUICK = [
    "Phân tích thu nhập và chi tiêu tháng này của mình",
    "Giải thích vì sao mình vượt ngân sách",
    "Gợi ý cách tiết kiệm dựa trên chi tiêu thực tế",
    "Mình nên chuẩn bị tiền thế nào cho các kỳ BNPL sắp tới?",
]


def _queue(prompt: str) -> None:
    st.session_state["_pending_prompt"] = prompt


def render(ctx: C.Ctx) -> None:
    C.hero("Guard AI – trợ lý tài chính", "Phân tích dựa trên số liệu thật trong ứng dụng, không bịa số")
    cfg = ai.get_config()
    configured = bool(cfg["api_key"])
    if not configured:
        st.warning(f"**Guard AI chưa được cấu hình.** Thiếu `{cfg['key_name']}`. Hãy tạo file `.env` từ `.env.example` "
                   "(hoặc dùng Streamlit Secrets) rồi khởi động lại. Các chức năng quản lý chi tiêu, BNPL, "
                   "kiểm tra trước khi mua vẫn hoạt động bình thường.", icon="🔑")
    else:
        st.caption(f"Nhà cung cấp: {cfg['provider']} · mô hình: {cfg['model']}. Số liệu tài chính của bạn "
                   "(tóm tắt) sẽ được gửi tới nhà cung cấp này khi bạn đặt câu hỏi.")

    extra = {}
    chk = st.session_state.get("check_result")
    if chk:
        extra["kiem_tra_truoc_khi_mua_gan_nhat"] = fin.summarize_assessment(chk)
        st.info(f"Guard AI đang thấy kết quả kiểm tra gần nhất: «{chk['item']}» – {chk['label']}.", icon="🛒")

    cols = st.columns(len(QUICK))
    for c, q in zip(cols, QUICK):
        c.button(q, key=f"q_{q}", on_click=_queue, args=(q,))

    hist = st.session_state.setdefault("chat", [])
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Hỏi Guard AI về chi tiêu, ngân sách, BNPL…")
    prompt = prompt or st.session_state.pop("_pending_prompt", None)
    if prompt:
        hist.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            if not configured:
                reply = ("Guard AI chưa được cấu hình API key nên mình chưa thể trả lời. "
                         "Bạn vẫn có thể dùng đầy đủ các chức năng quản lý tài chính trong ứng dụng.")
                st.markdown(reply)
            else:
                try:
                    with st.spinner("Guard AI đang phân tích số liệu…"):
                        reply = ai.ask(hist, ai.build_context(ctx.data, ctx.month, ctx.today, extra))
                    st.markdown(reply)
                except ai.AIError as e:
                    reply = f"⚠️ {e}"
                    st.error(str(e))
        hist.append({"role": "assistant", "content": reply})

    c1, c2 = st.columns([1, 3])
    if hist and c1.button("🧹 Xóa hội thoại"):
        st.session_state["chat"] = []
        st.rerun()
    with st.expander("Dữ liệu Guard AI được phép dùng"):
        st.caption("Đây là số liệu do Python tính từ cơ sở dữ liệu, gửi kèm mỗi câu hỏi.")
        st.json(ai.build_context(ctx.data, ctx.month, ctx.today, extra), expanded=False)

