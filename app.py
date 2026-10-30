"""장보기 알림메모 — 실행: streamlit run app.py
GitHub 저장소에 app.py와 requirements.txt를 올린 뒤 Streamlit Community Cloud에 배포.
배포 URL을 QR로 열면 같은 앱이 실행됩니다. 앱 내부 QR에는 실제 배포 URL을 입력하세요.
데이터는 URL의 무작위 list 키별로 SQLite에 저장합니다. 같은 링크는 같은 목록을 공유합니다.
주의: Cloud 로컬 디스크는 재배포/재시작 때 초기화될 수 있습니다. 영구 저장용 DB는 별도 연동 필요.
URL을 가진 사람은 목록을 수정할 수 있으므로 개인 목록 링크를 공개하지 마세요.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import sqlite3
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import qrcode
import streamlit as st

st.set_page_config(page_title="장보기 메모", page_icon="🛒", layout="centered", initial_sidebar_state="collapsed")

CATEGORIES = ["🥬 야채", "🍎 과일", "🥩 육류", "🐟 수산", "🥛 유제품·달걀", "🍚 곡류·식품", "🧴 생활용품", "📦 기타"]
PRIORITIES = {1: "1 · 꼭 필요", 2: "2 · 가격 보고", 3: "3 · 저렴하면"}
DB_PATH = os.environ.get("SHOPPING_DB_PATH", "shopping_memo.sqlite3")
PAGE_SIZE = 3


def money_total(unit_price: int, quantity: float) -> int:
    return int((Decimal(str(unit_price)) * Decimal(str(quantity))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_key TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL,
            priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 3),
            target_price INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'todo', unit_price INTEGER,
            quantity REAL, amount INTEGER, created_at TEXT NOT NULL, purchased_at TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_list_status ON items(list_key,status)")


init_db()
raw_key = st.query_params.get("list", "")
if not (16 <= len(raw_key) <= 100 and all(c.isalnum() or c in "-_" for c in raw_key)):
    raw_key = secrets.token_urlsafe(18)
    st.query_params["list"] = raw_key
LIST_KEY = raw_key


def records():
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM items WHERE list_key=? ORDER BY priority,id", (LIST_KEY,))]


def update_status(item_id, status):
    with connect() as conn:
        conn.execute("UPDATE items SET status=?,unit_price=NULL,quantity=NULL,amount=NULL,purchased_at=NULL WHERE id=? AND list_key=?", (status, item_id, LIST_KEY))


def shared_url(base):
    parts = urlsplit(base.strip())
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise ValueError("https://로 시작하는 실제 앱 주소를 입력하세요.")
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["list"] = LIST_KEY
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))


st.markdown("""<style>
[data-testid="stAppViewContainer"] {background:#f6f8f5;}
.block-container {max-width:570px;padding:0.65rem 0.75rem 0.5rem;}
header[data-testid="stHeader"] {height:0;min-height:0;background:transparent;}
#MainMenu,footer,[data-testid="stToolbar"] {display:none;}
[data-testid="stVerticalBlock"] {gap:0.35rem;}
[data-testid="stHorizontalBlock"] {gap:0.4rem;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width:0!important;}
@media(max-width:640px){
[data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {width:auto!important;flex:1 1 0!important;}
}
.stButton>button {min-height:2.35rem;padding:0.2rem 0.35rem;font-size:0.87rem;}
[data-testid="stForm"] {padding:0.65rem;}
[data-testid="stDialog"] [role="dialog"] {max-height:90dvh;overflow-y:auto;}
h3 {padding:0!important;margin:0!important;font-size:1.15rem!important;}
p {margin-bottom:0.2rem;}
.total {background:#153e35;color:white;border-radius:14px;padding:12px 15px;display:flex;justify-content:space-between;align-items:center;}
.total strong {font-size:1.55rem;}
.mini {color:#607367;font-size:0.76rem;}
.item-title {font-weight:700;font-size:0.98rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
</style>""", unsafe_allow_html=True)


@st.dialog("＋ 장보기 메모")
def add_dialog():
    with st.form("add_form", clear_on_submit=True):
        category = st.selectbox("카테고리", CATEGORIES)
        name = st.text_input("상품명", max_chars=60, placeholder="예: 양파 3개 / 우유 1L")
        priority = st.select_slider("중요도", options=[1, 2, 3], value=2, format_func=lambda x: PRIORITIES[x])
        target = st.number_input("구매 기준 단가 (원 · 0이면 미설정)", min_value=0, max_value=100000000, value=0, step=100)
        st.caption("기준 단가를 넘으면 담기 전 알려드려요. 수량 단위는 가격표 기준입니다.")
        submitted = st.form_submit_button("메모 추가", use_container_width=True, type="primary")
        if submitted:
            if not name.strip():
                st.error("상품명을 입력해 주세요.")
            else:
                with connect() as conn:
                    conn.execute("INSERT INTO items(list_key,name,category,priority,target_price,created_at) VALUES(?,?,?,?,?,?)", (LIST_KEY, name.strip(), category, priority, int(target), datetime.now().isoformat(timespec="seconds")))
                st.rerun()


@st.dialog("🛒 가격·수량 확인")
def purchase_dialog(item):
    st.write(f"**{item['name']}** · {PRIORITIES[item['priority']]}")
    if item["target_price"]:
        st.caption(f"구매 기준 단가: {item['target_price']:,}원")
    price = st.number_input("단가 (원)", min_value=0, max_value=100000000, value=int(item["target_price"] or 0), step=100, key=f"price_{item['id']}")
    quantity = st.number_input("수량 (개·팩·kg 등 가격표 단위)", min_value=0.01, max_value=100000.0, value=1.0, step=1.0, format="%.2f", key=f"qty_{item['id']}")
    amount = money_total(price, quantity)
    st.info(f"이 상품 합계  {amount:,}원")
    over = item["target_price"] > 0 and price > item["target_price"]
    if over:
        st.warning("기준보다 비싸요. 이번에는 보류해도 괜찮아요.")
    elif item["priority"] in (2, 3):
        st.caption("가격이 부담되면 오른쪽 ‘보류’를 눌러 다음에 구매하세요.")
    confirmed = st.checkbox("기준보다 비싸지만 구매할게요", key=f"confirm_{item['id']}") if over else True
    a, b = st.columns(2)
    if a.button("카트에 담기", type="primary", use_container_width=True, disabled=not confirmed):
        with connect() as conn:
            conn.execute("UPDATE items SET status='cart',unit_price=?,quantity=?,amount=?,purchased_at=? WHERE id=? AND list_key=? AND status IN ('todo','hold')", (int(price), float(quantity), amount, datetime.now().isoformat(timespec="seconds"), item["id"], LIST_KEY))
        st.rerun()
    if b.button("비싸요 · 보류", use_container_width=True):
        update_status(item["id"], "hold")
        st.rerun()


@st.dialog("메모 관리")
def manage_dialog(item):
    st.write(item["name"])
    st.caption("실제로 카트에 담은 상품은 ‘담기’에서 가격과 수량을 입력하세요.")
    a, b = st.columns(2)
    if a.button("목록으로 복귀" if item["status"] == "hold" else "다음에 · 보류", use_container_width=True):
        update_status(item["id"], "todo" if item["status"] == "hold" else "hold")
        st.rerun()
    if b.button("잘못 쓴 메모 삭제", use_container_width=True):
        with connect() as conn:
            conn.execute("DELETE FROM items WHERE id=? AND list_key=? AND status!='cart'", (item["id"], LIST_KEY))
        st.rerun()


@st.dialog("🔗 QR로 같은 목록 열기")
def qr_dialog():
    st.caption("배포 후 주소창의 앱 URL을 붙여넣으세요. 이 QR을 스캔하면 현재 목록이 열립니다.")
    base = st.text_input("배포된 앱 주소", value=st.session_state.get("base_url", ""), placeholder="https://your-app.streamlit.app")
    if base:
        try:
            url = shared_url(base)
            st.session_state["base_url"] = base
            buffer = io.BytesIO()
            qrcode.make(url).save(buffer, format="PNG")
            st.image(buffer.getvalue(), width=190)
            st.link_button("같은 목록 열기", url)
            st.download_button("QR 이미지 저장", buffer.getvalue(), "shopping-qr.png", "image/png")
            st.code(url, language=None)
        except ValueError as exc:
            st.error(str(exc))
    st.warning("링크를 아는 사람은 함께 수정할 수 있어요. 로컬 저장은 재배포 시 사라질 수 있습니다.")


@st.dialog("장보기 마무리")
def finish_dialog(cart):
    total = sum(row["amount"] or 0 for row in cart)
    st.write(f"카트 **{len(cart)}종 · {total:,}원**")
    st.caption("확정하면 카트를 비우고 완료 기록에 보관합니다. 보류·미구매 메모는 유지됩니다.")
    payload = json.dumps({"total_won": total, "items": cart}, ensure_ascii=False, indent=2)
    st.download_button("현재 카트 백업 (.json)", payload, "shopping-cart.json", "application/json", use_container_width=True)
    if st.button("장보기 완료 · 기록 보관", type="primary", use_container_width=True):
        with connect() as conn:
            conn.execute("UPDATE items SET status='done' WHERE list_key=? AND status='cart'", (LIST_KEY,))
        st.rerun()


rows = records()
cart = [r for r in rows if r["status"] == "cart"]
total = sum(r["amount"] or 0 for r in cart)
st.markdown("### 🛒 장보기 메모")
st.markdown(f'<div class="total"><span>현재 카트 · {len(cart)}종</span><strong>{total:,}원</strong></div>', unsafe_allow_html=True)
a, b, c = st.columns([1, 1, 1])
if a.button("＋ 메모", use_container_width=True, type="primary"):
    add_dialog()
if b.button("QR 공유", use_container_width=True):
    qr_dialog()
if c.button("완료", use_container_width=True, disabled=not cart):
    finish_dialog(cart)

view = st.segmented_control("보기", ["살 것", "보류", "카트", "기록"], default="살 것", label_visibility="collapsed", key="view") or "살 것"
status = {"살 것": "todo", "보류": "hold", "카트": "cart", "기록": "done"}[view]
selected = [r for r in rows if r["status"] == status]
if status in ("cart", "done"):
    selected.sort(key=lambda r: r["purchased_at"] or "", reverse=True)
page_key = f"page_{status}"
pages = max(1, (len(selected) + PAGE_SIZE - 1) // PAGE_SIZE)
st.session_state[page_key] = max(0, min(st.session_state.get(page_key, 0), pages - 1))
page = st.session_state[page_key]

# 한 번에 3개만 표시하여 본문 길이를 제한합니다. 작은 기기·큰 글꼴·키보드에서는 스크롤이 생길 수 있습니다.
with st.container(height=265, border=False):
    if not selected:
        st.info({"todo": "살 것을 ＋ 메모로 추가해 주세요.", "hold": "비싸서 보류한 상품이 여기 모여요.", "cart": "담기를 누르면 가격·수량과 함께 여기에 표시돼요.", "done": "완료한 구매 기록이 여기 남아요."}[status])
    for item in selected[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        with st.container(border=True):
            left, right = st.columns([3, 2])
            with left:
                st.text(item["name"] if len(item["name"]) <= 20 else item["name"][:19] + "…", help=item["name"])
                if status in ("cart", "done"):
                    st.caption(f"{item['unit_price']:,}원 × {item['quantity']:g} = {item['amount']:,}원")
                else:
                    target = f" · ≤{item['target_price']:,}원" if item["target_price"] else ""
                    st.caption(f"{item['category']} · 중요 {item['priority']}{target}")
            with right:
                if status in ("todo", "hold"):
                    x, y = st.columns([1, 1])
                    if x.button("담기", key=f"buy_{item['id']}", use_container_width=True):
                        purchase_dialog(item)
                    if y.button("⋯", key=f"more_{item['id']}", use_container_width=True):
                        manage_dialog(item)
                elif status == "cart":
                    if st.button("담기 취소", key=f"undo_{item['id']}", use_container_width=True):
                        update_status(item["id"], "todo")
                        st.rerun()
                else:
                    st.caption((item["purchased_at"] or "")[:10])

prev, middle, nxt = st.columns([1, 2, 1])
if prev.button("‹ 이전", use_container_width=True, disabled=page == 0):
    st.session_state[page_key] -= 1
    st.rerun()
middle.markdown(f"<div class='mini' style='text-align:center;padding-top:9px'>{len(selected)}개 · {page + 1}/{pages}</div>", unsafe_allow_html=True)
if nxt.button("다음 ›", use_container_width=True, disabled=page >= pages - 1):
    st.session_state[page_key] += 1
    st.rerun()
st.caption("1 꼭 필요 · 2 가격 보고 · 3 저렴하면 | 단가 × 수량 = 합계")
