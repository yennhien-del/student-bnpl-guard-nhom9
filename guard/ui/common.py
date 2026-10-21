"""Thành phần giao diện dùng chung."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import streamlit as st

from guard import db, finance as fin

PALETTE = ["#3478F6", "#142D4E", "#5AA9FF", "#22B8A5", "#F5A623", "#EF5B5B", "#8E7CC3", "#9AA7B8"]


@dataclass
class Ctx:
    conn: object
    data: fin.FinanceData
    today: date
    month: str


def today_vn() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:
        return date.today()


def month_options(today: date) -> list[str]:
    cur = fin.month_key(today)
    return [fin.add_months(cur, k) for k in range(-12, 7)]


# ---- hiển thị ---------------------------------------------------------------
def show_df(df: pd.DataFrame, **kw) -> None:
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def show_chart(fig, key=None) -> None:
    try:
        st.plotly_chart(fig, width="stretch", key=key)
    except Exception:
        st.plotly_chart(fig, use_container_width=True, key=key)


def style_fig(fig, height=340):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=36, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#142D4E"),
                      legend=dict(orientation="h", y=-0.18), colorway=PALETTE)
    fig.update_yaxes(gridcolor="#E6EBF3", zeroline=False)
    fig.update_xaxes(gridcolor="#E6EBF3")
    return fig


def hero(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="hero"><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>',
                unsafe_allow_html=True)


def kpi(label: str, value: str, sub: str = "", tone: str = "") -> None:
    st.markdown(f'<div class="kpi {tone}"><div class="l">{html.escape(label)}</div>'
                f'<div class="v">{html.escape(value)}</div><div class="s">{html.escape(sub)}</div></div>',
                unsafe_allow_html=True)


def alert(level: str, text: str) -> None:
    icon = {"danger": "⛔", "warning": "⚠️", "info": "ℹ️", "success": "✅"}.get(level, "")
    st.markdown(f'<div class="al {level}">{icon} {html.escape(text)}</div>', unsafe_allow_html=True)


def money_cols(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = [fin.fmt_vnd(x) for x in out[c]]
    return out


def vnd_input(label, key, value=0, step=10_000, max_value=None, disabled=False):
    kw = {"max_value": int(max_value)} if max_value is not None else {}
    return st.number_input(label, min_value=0, value=int(value), step=int(step), key=key,
                           disabled=disabled, **kw)


# ---- thông báo & thao tác ------------------------------------------------------
def flash(kind: str, msg: str) -> None:
    st.session_state.setdefault("_flash", []).append((kind, msg))


def show_flash() -> None:
    for kind, msg in st.session_state.pop("_flash", []):
        getattr(st, kind)(msg, icon={"success": "✅", "error": "⛔", "warning": "⚠️", "info": "ℹ️"}[kind])


def pick_row(df: pd.DataFrame, label: str, key: str, fmt):
    """Chọn một bản ghi để sửa/xóa. Trả về Series hoặc None (= thêm mới)."""
    if df.empty:
        return None
    ids = [None] + [int(i) for i in df["id"]]
    lookup = {int(r["id"]): r for r in df.to_dict("records")}
    if st.session_state.get(key) not in ids:
        st.session_state[key] = None
    rid = st.selectbox(label, ids, key=key,
                       format_func=lambda i: "➕ Thêm mới" if i is None else fmt(lookup[i]))
    return None if rid is None else lookup[rid]


def delete_cb(table: str, rid: int, select_key: str | None = None, ok: str = "Đã xóa.") -> None:
    conn = db.connect()
    try:
        db.delete_row(conn, table, rid)
        flash("success", ok)
    except Exception as e:  # noqa: BLE001
        flash("error", f"Không thể xóa: {e}")
    finally:
        conn.close()
    if select_key:
        st.session_state[select_key] = None


def delete_controls(table: str, rid: int, select_key: str, what: str) -> None:
    sure = st.checkbox(f"Tôi xác nhận xóa {what}", key=f"del_ok_{table}_{rid}")
    st.button("🗑️ Xóa", key=f"del_btn_{table}_{rid}", disabled=not sure, on_click=delete_cb,
              args=(table, rid, select_key, f"Đã xóa {what}."))


def run_save(fn, *args, ok="Đã lưu.", **kw):
    """Chạy hàm lưu; lỗi nhập liệu hiện thông báo, thành công thì tải lại trang."""
    try:
        res = fn(*args, **kw)
    except ValueError as e:
        st.error(str(e), icon="⛔")
        return None
    except Exception as e:  # noqa: BLE001
        st.error(f"Lỗi cơ sở dữ liệu: {e}", icon="⛔")
        return None
    flash("success", ok)
    st.rerun()
    return res


def date_input(label, value, key=None, **kw):
    return st.date_input(label, value=value, format="DD/MM/YYYY", key=key, **kw)
