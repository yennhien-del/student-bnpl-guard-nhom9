"""Student BNPL Guard – chạy: streamlit run app.py"""
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv không bắt buộc
    pass

from guard import db, finance as fin
from guard.ui import bnpl, budget, chat, check, common, dashboard, reports, settings, spending, styles

st.set_page_config(page_title="Student BNPL Guard", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = {
    "📊 Tổng quan": dashboard.render,
    "💰 Ngân sách": budget.render,
    "🧾 Chi tiêu": spending.render,
    "💳 BNPL": bnpl.render,
    "🛒 Kiểm tra trước khi mua": check.render,
    "🤖 Guard AI": chat.render,
    "📑 Báo cáo": reports.render,
    "⚙️ Cài đặt": settings.render,
}


def main() -> None:
    styles.inject()
    conn = db.connect()
    try:
        db.init_db(conn)
        today = common.today_vn()
        cur = fin.month_key(today)
        with st.sidebar:
            st.markdown('<div class="brand"><div class="logo">🛡️</div><div><div class="t1">Student BNPL Guard</div>'
                        '<div class="t2">Chi tiêu thông minh cho sinh viên</div></div></div>', unsafe_allow_html=True)
            page = st.radio("Điều hướng", list(PAGES), key="nav", label_visibility="collapsed")
            months = common.month_options(today)
            month = st.selectbox("Tháng làm việc", months, index=months.index(cur), key="month",
                                 format_func=fin.fmt_month)
            st.caption(f"Hôm nay: {fin.fmt_date(today)} · Đơn vị: VNĐ")
        ctx = common.Ctx(conn=conn, data=db.load_data(conn), today=today, month=month)
        common.show_flash()
        PAGES[page](ctx)
    finally:
        conn.close()


main()
