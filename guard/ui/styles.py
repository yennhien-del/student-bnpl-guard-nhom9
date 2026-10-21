"""CSS phong cách fintech cho Student BNPL Guard."""
import streamlit as st

CSS = """
<style>
:root{--navy:#142D4E;--blue:#3478F6;--bg:#F5F7FB;--muted:#6B7A90;--green:#1FA971;--amber:#E39A12;--red:#E5484D;}
.stApp{background:var(--bg);}
.block-container{padding-top:1.4rem;max-width:1200px;}
h1,h2,h3,h4{color:var(--navy);letter-spacing:-.01em;}

/* Sidebar */
section[data-testid="stSidebar"]{background:var(--navy);}
section[data-testid="stSidebar"] *{color:#E8EEF8;}
section[data-testid="stSidebar"] [data-baseweb="select"] *{color:#142D4E !important;}
section[data-testid="stSidebar"] div[role="radiogroup"]{gap:2px;}
section[data-testid="stSidebar"] div[role="radiogroup"] label{padding:9px 12px;border-radius:10px;width:100%;}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover{background:rgba(255,255,255,.10);}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){background:var(--blue);}
.brand{display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;}
.brand .logo{background:var(--blue);border-radius:12px;width:40px;height:40px;display:flex;align-items:center;justify-content:center;font-size:22px;}
.brand .t1{font-weight:700;font-size:1.05rem;line-height:1.1;}
.brand .t2{font-size:.75rem;opacity:.75;}

/* Hero */
.hero{background:linear-gradient(135deg,#142D4E 0%,#2459B8 60%,#3478F6 100%);color:#fff;border-radius:18px;
 padding:20px 26px;margin-bottom:18px;box-shadow:0 6px 18px rgba(20,45,78,.18);}
.hero h1{color:#fff;margin:0;font-size:1.55rem;padding:0;}
.hero p{margin:4px 0 0 0;opacity:.85;font-size:.92rem;}

/* KPI */
.kpi{background:#fff;border-radius:16px;padding:15px 18px;box-shadow:0 2px 10px rgba(20,45,78,.07);
 border-left:5px solid var(--blue);margin-bottom:12px;min-height:106px;}
.kpi .l{color:var(--muted);font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;}
.kpi .v{color:var(--navy);font-size:1.55rem;font-weight:700;margin:3px 0;word-break:break-word;}
.kpi .s{color:var(--muted);font-size:.8rem;}
.kpi.good{border-left-color:var(--green);} .kpi.warn{border-left-color:var(--amber);}
.kpi.bad{border-left-color:var(--red);} .kpi.bad .v{color:var(--red);}
.kpi.navy{border-left-color:var(--navy);}

/* Alert */
.al{border-radius:12px;padding:10px 14px;margin:6px 0;font-size:.92rem;border:1px solid transparent;}
.al.danger{background:#FDECEC;border-color:#F5C2C4;color:#8A1F24;}
.al.warning{background:#FFF5E0;border-color:#F4D79B;color:#7A5200;}
.al.info{background:#E8F0FE;border-color:#BFD3FB;color:#1B3F8B;}
.al.success{background:#E5F6EE;border-color:#B5E4CD;color:#146B48;}

/* Badge */
.badge{display:inline-block;padding:6px 16px;border-radius:999px;font-weight:700;font-size:1rem;}
.badge.low{background:#E5F6EE;color:#146B48;} .badge.caution{background:#FFF5E0;color:#7A5200;}
.badge.high{background:#FDECEC;color:#8A1F24;} .badge.insufficient{background:#EDF0F5;color:#4A5568;}

/* Budget bar */
.bb{background:#fff;border-radius:12px;padding:10px 14px;margin-bottom:8px;box-shadow:0 1px 6px rgba(20,45,78,.06);}
.bb .row{display:flex;justify-content:space-between;font-size:.9rem;color:var(--navy);gap:8px;flex-wrap:wrap;}
.bb .track{background:#E6EBF3;border-radius:999px;height:9px;margin-top:6px;overflow:hidden;}
.bb .fill{height:9px;border-radius:999px;}
.card{background:#fff;border-radius:16px;padding:16px 18px;box-shadow:0 2px 10px rgba(20,45,78,.07);margin-bottom:12px;}
.muted{color:var(--muted);font-size:.85rem;}

@media (max-width:768px){
 .block-container{padding-left:.8rem;padding-right:.8rem;}
 .hero{padding:14px 16px;} .hero h1{font-size:1.2rem;}
 .kpi{min-height:0;padding:12px 14px;} .kpi .v{font-size:1.25rem;}
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
