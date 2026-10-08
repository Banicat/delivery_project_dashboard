"""
예제: 신규 권역 성장 기회
5주차 설계 예제의 쿼리를 SQLite로 바꾸고, 6주차 리포트의 KPI 카드 3개 · 차트 3장을
필터에 반응하도록 옮겨 둔 코드입니다. 

탭 3개(개요 · 탐색 · 액션) 뼈대가 들어 있습니다.
- ✏️표시: 내 5주차 · 6주차 결과물로 변경할 곳
- [블록 A] · [블록 B] · [블록 C]: Gemini에게 받은 블록으로 통째로 바꿀 곳
  (===== 시작 줄과 ===== 끝 줄 사이를 지우고 받은 블록을 붙임, 첫 줄은 맨 앞에 빈칸 없이)
"""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

ACCENT, GRAY = "#1F3A5F", "#BDBDBD"
px.defaults.color_discrete_map = {
    "INSTA_첫주문쿠폰": ACCENT, "organic": "#8C8C8C", "NAVER_검색광고": "#A6A6A6",
    "GOOGLE_앱설치": GRAY, "친구초대": "#DADADA", "Android": "#8C8C8C", "iOS": GRAY,
}
px.defaults.color_discrete_sequence = [GRAY]

st.set_page_config(page_title="신규 권역 성장 기회 대시보드", layout="wide")
st.title("신규 권역 성장 기회 대시보드")                                  # ✏️ 6주차 메인 제목
st.caption("가입월 · 가입 채널 · 플랫폼별 | 2025.09 ~ 2026.07 가입자")     # ✏️ 6주차 부제

# ------------------------------------------------------------
# 0. 필요한 데이터만 추출 — 쓸 테이블과 컬럼만 메모리 DB에 올리고, 정제 테이블을 처음 한 번만 만듦
# ------------------------------------------------------------
DATA_DIR = "data"                          # 원본 CSV를 넣어 둔 폴더
NEEDED = {                                 # ✏️ 이번 대시보드에 필요한 테이블과 컬럼 (쿼리에 쓰는 것만)
    "app_events": ["event_datetime", "customer_id", "session_id", "event_name",
                   "platform", "traffic_source", "campaign_name"],
    "orders": ["customer_id", "order_datetime"],
}

@st.cache_resource
def get_db():                              # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events·odr을 생성(처음 한 번)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name, cols in NEEDED.items():
        # dtype=str: 고객 ID의 앞자리 0(0000002)이 숫자로 바뀌지 않게 글자로 읽음
        pd.read_csv(f"{DATA_DIR}/{name}.csv", usecols=cols, dtype=str).to_sql(name, con, index=False)
    # ✏️ 5주차 제외 규칙: 테스트 계정(T로 시작) 제외 · 이벤트 100건 이상인 비정상 세션 제외
    con.execute("""
        CREATE TABLE events AS
        SELECT *
          FROM app_events
         WHERE customer_id NOT LIKE 'T%'
           AND session_id NOT IN (SELECT session_id FROM app_events
                                   GROUP BY session_id HAVING COUNT(*) >= 100)
    """)
    con.execute("CREATE TABLE odr AS SELECT * FROM orders WHERE customer_id NOT LIKE 'T%'")
    # 고객별로 묶는 집계가 빨라지도록 customer_id에 인덱스를 붙임
    con.execute("CREATE INDEX idx_events_customer ON events(customer_id)")
    con.execute("CREATE INDEX idx_odr_customer ON odr(customer_id)")
    return con

# ------------------------------------------------------------
# 1. 데이터 준비 — 정제된 테이블을 SQL로 집계 (비율이 아니라 분자 · 분모 건수만)
# ------------------------------------------------------------
@st.cache_data
def query(sql):                            # SQL을 실행해 표로 돌려줌
    return pd.read_sql(sql, get_db())

# 고객별 가입일 · 가입 채널 · 플랫폼 (가입 이벤트 기준) - 두 쿼리 모두 사용
SQL_SIGNUP = """
su AS (
    SELECT customer_id,
           DATE(MIN(event_datetime))                    AS 가입일,
           MIN(COALESCE(campaign_name, traffic_source)) AS 가입채널,
           MIN(platform)                                AS 플랫폼
      FROM events
     WHERE event_name = 'sign_up'
     GROUP BY customer_id
)
"""

# ✏️ 가입월 × 가입 채널 × 플랫폼별 가입 후 30일 퍼널 (예제 Q1 · Q3)
SQL_SIGNUP_FUNNEL = f"""
WITH {SQL_SIGNUP},
ev AS (                                     -- 가입 후 30일 안의 행동
    SELECT DISTINCT e.customer_id, e.event_name
      FROM events e
      JOIN su ON e.customer_id = su.customer_id
     WHERE julianday(DATE(e.event_datetime)) - julianday(su.가입일) BETWEEN 0 AND 30
),
fo AS (                                     -- 고객별 첫 주문일
    SELECT customer_id, DATE(MIN(order_datetime)) AS 첫주문일
      FROM odr
     GROUP BY customer_id
)
SELECT strftime('%Y-%m', su.가입일) AS 가입월,
       su.가입채널,
       su.플랫폼,
       COUNT(DISTINCT su.customer_id)                                                         AS 가입자,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'view_restaurant' THEN su.customer_id END)    AS 식당조회,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'add_to_cart'     THEN su.customer_id END)    AS 장바구니,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'begin_checkout'  THEN su.customer_id END)    AS 결제시작,
       COUNT(DISTINCT CASE WHEN julianday(fo.첫주문일) - julianday(su.가입일) <= 30
                           THEN su.customer_id END)                                           AS 첫주문30일
  FROM su
  LEFT JOIN ev ON su.customer_id = ev.customer_id
  LEFT JOIN fo ON su.customer_id = fo.customer_id
 WHERE su.가입일 <= '2026-07-31'            -- 30일을 다 볼 수 있는 가입자만
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

# ✏️ 가입월 × 가입 채널 × 플랫폼별 30일 재주문 (예제 Q2, 분모가 첫 주문 고객이라 표를 따로 만듦)
SQL_REORDER = f"""
WITH {SQL_SIGNUP},
seq AS (
    SELECT customer_id, order_datetime,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_datetime) AS 순번,
           LEAD(order_datetime) OVER (PARTITION BY customer_id ORDER BY order_datetime) AS 다음주문
      FROM odr
)
SELECT strftime('%Y-%m', su.가입일) AS 가입월,
       su.가입채널,
       su.플랫폼,
       COUNT(*)                                                                          AS 첫주문고객,
       SUM(CASE WHEN julianday(DATE(seq.다음주문)) - julianday(DATE(seq.order_datetime)) <= 30
                THEN 1 ELSE 0 END)                                                       AS 재주문30일
  FROM seq
  JOIN su ON seq.customer_id = su.customer_id
 WHERE seq.순번 = 1
   AND seq.order_datetime < '2026-08-01'    -- 30일을 다 볼 수 있는 첫 주문만
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    return query(SQL_SIGNUP_FUNNEL), query(SQL_REORDER)

df, rd = load_data()                       # df: 가입 후 30일 퍼널 / rd: 30일 재주문

# 📌 AI 해설: 아래 AI_NOTES = {} 한 줄을 Gemini가 준 AI_NOTES = { … } 로 바꾸기
AI_NOTES = {
    "전체": "전체 2,774명을 기준으로 30일 첫 주문 전환율은 69.9%이며, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 67.4%였다. 플랫폼별로는 Android와 iOS 간 전환율 차이가 크지 않은 것으로 보인다. 상세한 마케팅 효과의 원인은 확인이 필요하다.",
    "Android": "Android 가입자는 1,502명으로 30일 첫 주문 전환율은 69.2%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 66.6%였다. 전체 평균 전환율과 유사한 수준을 보였다. OS별 세부 이용 성향의 차이에 대해서는 추가 확인이 필요하다.",
    "iOS": "iOS 가입자는 1,272명으로 30일 첫 주문 전환율은 70.7%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 68.2%였다. 전체 평균 대비 소폭 높거나 유사한 수준을 기록했다. 플랫폼 간 격차의 배경은 확인이 필요하다.",
    "organic": "organic 가입자는 847명으로 30일 첫 주문 전환율은 75.2%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 73.5%였다. 전체 평균 대비 첫 주문 및 재주문 전환율이 모두 높은 편에 속했다. 유입 경로별 품질 차이의 원인은 확인이 필요하다.",
    "INSTA_첫주문쿠폰": "INSTA_첫주문쿠폰 가입자는 739명으로 30일 첫 주문 전환율은 55.6%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 44.5%였다. 전체 및 다른 집단과 비교해 첫 주문과 재주문 지표가 모두 낮았으며 2026-01 가입월부터 나타났다. 저조한 성과의 구체적 요인은 확인이 필요하다.",
    "NAVER_검색광고": "NAVER_검색광고 가입자는 517명으로 30일 첫 주문 전환율은 76.4%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 72.6%였다. 전체 평균 대비 높은 첫 주문 전환율을 보였다. 매체별 효율 차이에 대한 원인은 확인이 필요하다.",
    "GOOGLE_앱설치": "GOOGLE_앱설치 가입자는 398명으로 30일 첫 주문 전환율은 73.6%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 72.7%였다. 전체 평균 대비 우수한 전환 성과를 기록했다. 캠페인 운영 방식과의 연관성은 확인이 필요하다.",
    "친구초대": "가입자가 273명으로 300명 미만이며 30일 첫 주문 전환율은 74.4%, 가장 낮은 단계 전환율은 첫주문고객에서 재주문30일로 이어지는 77.3%였다. 재주문율 측면에서는 다른 집단 대비 가장 높은 수준을 보였다. 높은 재주문 지표의 배경은 확인이 필요하다."
}
AI_SOURCE = "🤖 Gemini가 미리 만든 해설 · 전체 기간 기준"

# ------------------------------------------------------------
# 2. 사이드바 필터 — 두 표에 같은 조건을 적용
# ------------------------------------------------------------
SMALL = 100                                # ✏️ 이보다 가입자가 적은 집단은 "작은 집단"

if "reset" not in st.session_state:
    st.session_state.reset = 0

def reset_filters():                       # 번호가 바뀌면 위젯이 처음 상태로 새로 만들어짐
    st.session_state.reset += 1

n = st.session_state.reset
months = sorted(df["가입월"].unique())
channels = sorted(df["가입채널"].unique())
platforms = sorted(df["플랫폼"].unique())

st.sidebar.header("필터")
start, end = st.sidebar.select_slider("가입월", options=months,
                                      value=(months[0], months[-1]), key=f"기간_{n}")
sel_channels = st.sidebar.multiselect("가입 채널", channels, default=channels, key=f"채널_{n}")
sel_platforms = st.sidebar.multiselect("플랫폼", platforms, default=platforms, key=f"플랫폼_{n}")
with st.sidebar.expander("고급 설정"):
    base_start, base_end = st.select_slider(
        "평소 범위 기준 기간", options=months, value=(months[0], months[3]), key=f"기준_{n}",   # ✏️ 문제가 없던 기간
        help="문제가 없던 기간을 고르세요. 이 기간의 월별 값 범위를 '평소 범위'로 씁니다.")
    hide_small = st.checkbox(f"가입자 {SMALL}명 미만 집단 제외 (집단 비교 · 드릴다운)", key=f"작은집단_{n}")
st.sidebar.button("필터 초기화", on_click=reset_filters)

# 집단 조건(가입 채널 · 플랫폼)만 적용한 데이터 g · rg, 기간까지 적용한 데이터 f · rf
g = df[df["가입채널"].isin(sel_channels) & df["플랫폼"].isin(sel_platforms)]
f = g[(g["가입월"] >= start) & (g["가입월"] <= end)]
rg = rd[rd["가입채널"].isin(sel_channels) & rd["플랫폼"].isin(sel_platforms)]
rf = rg[(rg["가입월"] >= start) & (rg["가입월"] <= end)]

def label(selected, all_values):           # 조건 줄에 쓸 말: 모두 고르면 "전체"
    if len(selected) == len(all_values):
        return "전체"
    return ", ".join(selected) if selected else "선택 없음"

period = "전체" if (start, end) == (months[0], months[-1]) else f"{start} ~ {end}"
st.caption(f"🔎 보고 있는 조건: 가입월 {period} · 가입 채널 {label(sel_channels, channels)} · "
           f"플랫폼 {label(sel_platforms, platforms)}")

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()

def rate(a, b):
    return a / b * 100 if b else 0

# ------------------------------------------------------------
# 3. 화면 — 탭 3개
# ------------------------------------------------------------
tab_overview, tab_explore, tab_action = st.tabs(["📊 개요", "🔍 탐색", "✅ 액션"])

# ===== [블록 A] 개요 · KPI 카드 — 규칙 문장 단계에서 이 블록을 통째로 바꿈 =====
with tab_overview:
    st.caption("이 탭에서 볼 수 있는 것: 핵심 숫자와 그 숫자를 읽는 법, 6주차 리포트의 차트 3장 (필터 적용)")

    # 3-1. KPI 카드 — ✏️ 5주차 지표 3개
    t = f[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum()
    tr = rf[["첫주문고객", "재주문30일"]].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("30일 첫 주문 전환율", f"{rate(t['첫주문30일'], t['가입자']):.1f}%")
    c2.metric("식당 조회 → 장바구니 전환율", f"{rate(t['장바구니'], t['식당조회']):.1f}%")
    c3.metric("30일 재주문율", f"{rate(tr['재주문30일'], tr['첫주문고객']):.1f}%")

    # 지금 숫자 읽기 상자
    with st.container(border=True):
        st.markdown("**📏 지금 숫자 읽기**")
        
        # 월 목록 정렬 및 기간 체크
        active_months = sorted(f["가입월"].unique())
        
        if len(active_months) < 3:
            st.markdown("- 30일 첫 주문 전환율: 비교하려면 선택 기간을 3개월 이상 골라 주세요")
            st.markdown("- 식당 조회 → 장바구니 전환율: 비교하려면 선택 기간을 3개월 이상 골라 주세요")
        else:
            # 최근 3개월 추출
            recent_3m = active_months[-3:]
            f_3m = f[f["가입월"].isin(recent_3m)]
            t_3m = f_3m[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum()
            
            # 이번 값 계산
            curr_su = t_3m["가입자"]
            curr_ord = t_3m["첫주문30일"]
            curr_rate_ord = rate(curr_ord, curr_su)
            
            curr_view = t_3m["식당조회"]
            curr_cart = t_3m["장바구니"]
            curr_rate_cart = rate(curr_cart, curr_view)
            
            display_period = f"{recent_3m[0]} 가입월부터 3개월"
            
            # 기준 기간 데이터 처리 (g 데이터 기준 base_start ~ base_end)
            g_base = g[(g["가입월"] >= base_start) & (g["가입월"] <= base_end)]
            base_months = sorted(g_base["가입월"].unique())
            
            if len(base_months) < 3:
                msg_ord = "- 30일 첫 주문 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
                msg_cart = "- 식당 조회 → 장바구니 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
            else:
                # 월별로 묶어 분자/분모 합산 후 비율 계산 (분모가 0인 달은 제외)
                monthly_base = g_base.groupby("가입월")[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum().reset_index()
                
                # 첫주문 전환율 평소 범위 계산
                ord_rates = []
                for _, row in monthly_base.iterrows():
                    if row["가입자"] > 0:
                        ord_rates.append(row["첫주문30일"] / row["가입자"] * 100)
                
                # 장바구니 전환율 평소 범위 계산
                cart_rates = []
                for _, row in monthly_base.iterrows():
                    if row["식당조회"] > 0:
                        cart_rates.append(row["장바구니"] / row["식당조회"] * 100)
                
                if not ord_rates or not cart_rates:
                    msg_ord = "- 30일 첫 주문 전환율: 기준 기간 내 분모가 0이 아닌 월이 부족합니다."
                    msg_cart = "- 식당 조회 → 장바구니 전환율: 기준 기간 내 분모가 0이 아닌 월이 부족합니다."
                else:
                    ord_min, ord_max = min(ord_rates), max(ord_rates)
                    cart_min, cart_max = min(cart_rates), max(cart_rates)
                    
                    # 1) 첫 주문 전환율 문장 생성
                    diff_ord = curr_rate_ord - ((ord_min + ord_max) / 2) # 비교용 (낮으면/높으면/안이면)
                    if curr_rate_ord < ord_min:
                        comp_text_ord = f"평소 범위({ord_min:.1f}–{ord_max:.1f}%)보다 {ord_min - curr_rate_ord:.1f}%p 낮습니다"
                    elif curr_rate_ord > ord_max:
                        comp_text_ord = f"평소 범위({ord_min:.1f}–{ord_max:.1f}%)보다 {curr_rate_ord - ord_max:.1f}%p 높습니다"
                    else:
                        comp_text_ord = f"평소 범위({ord_min:.1f}–{ord_max:.1f}%) 내에 있습니다"
                    msg_ord = f"- 30일 첫 주문 전환율: {display_period} 30일 첫 주문 전환율은 {curr_rate_ord:.1f}%로, {comp_text_ord}"
                    
                    # 2) 장바구니 전환율 문장 생성
                    if curr_rate_cart < cart_min:
                        comp_text_cart = f"평소 범위({cart_min:.1f}–{cart_max:.1f}%)보다 {cart_min - curr_rate_cart:.1f}%p 낮습니다"
                    elif curr_rate_cart > cart_max:
                        comp_text_cart = f"평소 범위({cart_min:.1f}–{cart_max:.1f}%)보다 {curr_rate_cart - cart_max:.1f}%p 높습니다"
                    else:
                        comp_text_cart = f"평소 범위({cart_min:.1f}–{cart_max:.1f}%) 내에 있습니다"
                    msg_cart = f"- 식당 조회 → 장바구니 전환율: {display_period} 식당 조회 → 장바구니 전환율은 {curr_rate_cart:.1f}%로, {comp_text_cart}"
            
            st.markdown(msg_ord)
            st.markdown(msg_cart)
            
        st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {base_start} ~ {base_end} (월별 값)")
        
        with st.expander("🤖 AI 해설 · 전체", expanded=False):
            st.write(AI_NOTES.get("전체", "아직 해설이 없습니다."))
            st.caption(AI_SOURCE)
# ===== [블록 A] 끝 =====

with tab_overview:
    st.divider()

    # ✏️ 3-2. 차트 - 6주차 차트 ① 문제 · ② 원인 · ③ 제안
    left, right = st.columns(2)

    # ① 문제: 가입월별 30일 첫 주문 전환율
    m = f.groupby("가입월")[["가입자", "첫주문30일"]].sum().reset_index()
    m["첫주문전환율"] = (m["첫주문30일"] / m["가입자"] * 100).round(1)
    fig1 = px.line(m, x="가입월", y="첫주문전환율", markers=True, hover_data=["가입자"],
                   labels={"가입월": "가입월", "첫주문전환율": "30일 첫 주문 전환율(%)", "가입자": "가입자(명)"},
                   title="① 가입월별 30일 첫 주문 전환율")
    fig1.update_layout(xaxis_title="")
    fig1.update_xaxes(type="category")       # 가입월(2025-09)을 날짜가 아니라 글자 그대로 표시
    left.plotly_chart(fig1, width="stretch")

    # ② 원인: 가입 채널별 식당 조회 → 장바구니 전환율
    ch = f.groupby("가입채널")[["식당조회", "장바구니"]].sum().reset_index()
    ch["장바구니전환율"] = (ch["장바구니"] / ch["식당조회"] * 100).round(1)
    ch = ch.sort_values("장바구니전환율")
    fig2 = px.bar(ch, x="장바구니전환율", y="가입채널", orientation="h", text_auto=".1f",
                  hover_data=["식당조회"],
                  labels={"장바구니전환율": "식당 조회 → 장바구니 전환율(%)", "가입채널": "가입 채널",
                          "식당조회": "식당 조회 가입자(명)"},
                  title="② 가입 채널별 식당 조회 → 장바구니 전환율")
    fig2.update_xaxes(range=[0, ch["장바구니전환율"].max() * 1.2])
    fig2.update_layout(yaxis_title="")
    fig2.update_traces(marker_color=[ACCENT if c == "INSTA_첫주문쿠폰" else GRAY for c in ch["가입채널"]])
    fig2.update_xaxes(visible=False)
    right.plotly_chart(fig2, width="stretch")

    # ③ 제안: 가입 채널별 30일 재주문율
    rc = rf.groupby("가입채널")[["첫주문고객", "재주문30일"]].sum().reset_index()
    rc["재주문율"] = (rc["재주문30일"] / rc["첫주문고객"] * 100).round(1)
    rc = rc.sort_values("재주문율")
    fig3 = px.bar(rc, x="재주문율", y="가입채널", orientation="h", text_auto=".1f",
                  hover_data=["첫주문고객"],
                  labels={"재주문율": "30일 재주문율(%)", "가입채널": "가입 채널", "첫주문고객": "첫 주문 고객(명)"},
                  title="③ 가입 채널별 30일 재주문율")
    fig3.update_xaxes(range=[0, rc["재주문율"].max() * 1.2])
    fig3.update_layout(yaxis_title="")
    st.plotly_chart(fig3, width="stretch")

    # AI 해설을 만들 때 Gemini에 올릴 표 (필터와 관계없이 전체)
    with st.expander("📥 AI 해설용 데이터 내려받기"):
        st.download_button("가입 후 30일 퍼널 (가입월 × 가입 채널 × 플랫폼)",
                           df.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_퍼널.csv")
        st.download_button("30일 재주문 (가입월 × 가입 채널 × 플랫폼)",
                           rd.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_재주문.csv")

# ===== [블록 B] 탐색 — 집단 비교 · 드릴다운 단계에서 이 블록을 통째로 바꿈 =====
with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교와 드릴다운 — 어디서, 언제부터인가")
    
    compare_by = st.radio("비교 기준", ["가입채널", "플랫폼"], horizontal=True, key="explore_compare_by")
    col_name = "가입채널" if compare_by == "가입채널" else "플랫폼"
    
    # f 데이터에서 그룹별 퍼널 5단계 합계 계산
    grouped = f.groupby(col_name)[["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]].sum().reset_index()
    
    # 가입자 SMALL명 미만 집단 처리
    small_groups = grouped[grouped["가입자"] < SMALL][col_name].tolist()
    if hide_small:
        grouped = grouped[grouped["가입자"] >= SMALL]
        if small_groups:
            st.caption(f"제외한 집단: {', '.join(small_groups)} (가입자 {SMALL}명 미만)")
    
    if grouped.empty:
        st.warning("조건에 해당하는 집단이 없습니다.")
    else:
        # 남은 집단 중 SMALL명 미만인 집단이 있으면 경고 표시
        remaining_small = grouped[grouped["가입자"] < SMALL][col_name].tolist()
        if not hide_small and remaining_small:
            st.caption(f"⚠️ 가입자가 {SMALL}명 미만인 집단({', '.join(remaining_small)})이 포함되어 있어 값이 크게 흔들릴 수 있습니다.")
        
        # 좌우 컬럼 분할
        left_col, right_col = st.columns(2)
        
        # 1. 왼쪽: 누적 전환율(가입자 대비 %) 퍼널 (px.funnel)
        funnel_melted = []
        for _, row in grouped.iterrows():
            g_name = row[col_name]
            total_su = row["가입자"]
            stages = [
                ("가입자", total_su, 100.0 if total_su > 0 else 0),
                ("식당조회", row["식당조회"], row["식당조회"] / total_su * 100 if total_su > 0 else 0),
                ("장바구니", row["장바구니"], row["장바구니"] / total_su * 100 if total_su > 0 else 0),
                ("결제시작", row["결제시작"], row["결제시작"] / total_su * 100 if total_su > 0 else 0),
                ("첫주문30일", row["첫주문30일"], row["첫주문30일"] / total_su * 100 if total_su > 0 else 0),
            ]
            for stage_name, count_val, rate_val in stages:
                funnel_melted.append({
                    col_name: g_name,
                    "퍼널단계": stage_name,
                    "누적전환율": round(rate_val, 1),
                    "사람수": count_val
                })
        df_funnel = pd.DataFrame(funnel_melted)
        
        fig_funnel = px.funnel(
            df_funnel,
            x="누적전환율",
            y="퍼널단계",
            color=col_name,
            hover_data={"사람수": True, "누적전환율": True},
            labels={"누적전환율": "가입자 대비 누적 전환율(%)", "퍼널단계": "퍼널 단계", col_name: col_name, "사람수": "사람 수(명)"},
            title="집단별 누적 전환율 퍼널"
        )
        left_col.plotly_chart(fig_funnel, width="stretch")
        
        # 2. 오른쪽: 단계 전환율(직전 단계 대비 %) 막대 (barmode="group")
        step_melted = []
        for _, row in grouped.iterrows():
            g_name = row[col_name]
            su = row["가입자"]
            view = row["식당조회"]
            cart = row["장바구니"]
            checkout = row["결제시작"]
            order = row["첫주문30일"]
            
            # 가입자 -> 식당조회
            r1 = view / su * 100 if su > 0 else 0
            step_melted.append({col_name: g_name, "단계이동": "가입 → 식당조회", "단계전환율": round(r1, 1), "직전단계사람수": su})
            
            # 식당조회 -> 장바구니
            r2 = cart / view * 100 if view > 0 else 0
            step_melted.append({col_name: g_name, "단계이동": "식당조회 → 장바구니", "단계전환율": round(r2, 1), "직전단계사람수": view})
            
            # 장바구니 -> 결제시작
            r3 = checkout / cart * 100 if cart > 0 else 0
            step_melted.append({col_name: g_name, "단계이동": "장바구니 → 결제시작", "단계전환율": round(r3, 1), "직전단계사람수": cart})
            
            # 결제시작 -> 첫주문30일
            r4 = order / checkout * 100 if checkout > 0 else 0
            step_melted.append({col_name: g_name, "단계이동": "결제시작 → 첫주문30일", "단계전환율": round(r4, 1), "직전단계사람수": checkout})
            
        df_step = pd.DataFrame(step_melted)
        
        fig_step = px.bar(
            df_step,
            x="단계이동",
            y="단계전환율",
            color=col_name,
            barmode="group",
            text_auto=".1f",
            hover_data={"직전단계사람수": True, "단계전환율": True},
            labels={"단계전환율": "직전 단계 대비 전환율(%)", "단계이동": "단계 이동", col_name: col_name, "직전단계사람수": "직전 단계 사람 수(명)"},
            title="집단별 직전 단계 대비 전환율"
        )
        fig_step.update_layout(xaxis_title="")
        right_col.plotly_chart(fig_step, width="stretch")

    st.divider()
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    available_groups = grouped[col_name].tolist()
    if not available_groups:
        st.info("선택 가능한 집단이 없습니다.")
    else:
        drill_col1, drill_col2 = st.columns(2)
        selected_group = drill_col1.selectbox("자세히 볼 집단", available_groups, key="drill_selected_group")
        
        stage_options = [
            "가입 → 30일 첫 주문",
            "가입 → 식당조회",
            "식당조회 → 장바구니",
            "장바구니 → 결제시작",
            "결제시작 → 30일 첫 주문"
        ]
        selected_stage = drill_col2.selectbox("단계", stage_options, key="drill_selected_stage")

        other_col = "플랫폼" if col_name == "가입채널" else "가입채널"
        sub_f = f[f[col_name] == selected_group]

        # 차트 ① 데이터 준비
        monthly_stage = sub_f.groupby(["가입월", other_col])[[
            "가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"
        ]].sum().reset_index()

        stage_mapping = {
            "가입 → 30일 첫 주문": ("가입자", "첫주문30일"),
            "가입 → 식당조회": ("가입자", "식당조회"),
            "식당조회 → 장바구니": ("식당조회", "장바구니"),
            "장바구니 → 결제시작": ("장바구니", "결제시작"),
            "결제시작 → 30일 첫 주문": ("결제시작", "첫주문30일")
        }
        den_col, num_col = stage_mapping[selected_stage]

        chart1_rows = []
        for _, row in monthly_stage.iterrows():
            den_val = row[den_col]
            num_val = row[num_col]
            rate_val = (num_val / den_val * 100) if den_val > 0 else None
            chart1_rows.append({
                "가입월": row["가입월"],
                other_col: row[other_col],
                "전환율": round(rate_val, 1) if rate_val is not None else None,
                "직전단계사람수": den_val
            })
        df_chart1 = pd.DataFrame(chart1_rows)

        fig1_drill = px.line(
            df_chart1,
            x="가입월",
            y="전환율",
            color=other_col,
            markers=True,
            hover_data=["직전단계사람수"],
            labels={"가입월": "가입월", "전환율": "전환율(%)", other_col: other_col, "직전단계사람수": "직전 단계 사람 수(명)"},
            title=f"① {selected_group}의 가입월별 {selected_stage} 전환율 — {other_col}별로 쪼개 보기"
        )
        fig1_drill.update_layout(xaxis_title="")
        fig1_drill.update_xaxes(type="category")
        st.plotly_chart(fig1_drill, width="stretch")
        st.caption("모든 갈래가 함께 움직였다면, 그 축은 원인이 아닙니다.")

        # 차트 ② 데이터 준비 (가입월별 가입자 수 쌓기: 선택 집단 vs 그 외)
        f_copy = f.copy()
        f_copy["그룹구분"] = f_copy[col_name].apply(lambda x: selected_group if x == selected_group else "그 외")
        monthly_stack = f_copy.groupby(["가입월", "그룹구분"])["가입자"].sum().reset_index()

        fig2_drill = px.bar(
            monthly_stack,
            x="가입월",
            y="가입자",
            color="그룹구분",
            barmode="stack",
            color_discrete_map={selected_group: "#1f3755", "그 외": "#b0b0b0"},
            labels={"가입월": "가입월", "가입자": "가입자 수(명)", "그룹구분": "집단 구분"},
            title=f"② 가입월별 가입자 수 구성 ({selected_group} vs 그 외)"
        )
        fig2_drill.update_layout(xaxis_title="")
        fig2_drill.update_xaxes(type="category")
        st.plotly_chart(fig2_drill, width="stretch")
        st.caption("전체 전환율이 움직인 시점에 이 집단의 비중이 함께 바뀌었다면 구성 변화가 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

        with st.expander(f"🤖 AI 해설 · {selected_group}", expanded=False):
            st.write(AI_NOTES.get(selected_group, "이 집단의 해설은 아직 없습니다."))
            st.caption(AI_SOURCE)
# ===== [블록 B] 끝 =====

# ===== [블록 C] 액션 — 액션 카드 단계에서 이 줄 아래부터 파일 끝까지를 받은 블록으로 바꿈 =====
with tab_action:
    st.caption("측정 KPI의 현재 값은 선택한 기간의 마지막 3개월로 계산합니다")
    
    # 사이드바 기간(start ~ end)만 적용한 데이터 준비 (채널/플랫폼 필터 무시)
    df_action_su = df[(df["가입월"] >= start) & (df["가입월"] <= end)]
    rd_action_re = rd[(rd["가입월"] >= start) & (rd["가입월"] <= end)]
    
    # 마지막 3개월 추출
    active_months_action = sorted(df_action_su["가입월"].unique())
    if len(active_months_action) >= 3:
        target_3m = active_months_action[-3:]
        df_3m = df_action_su[df_action_su["가입월"].isin(target_3m)]
        rd_3m = rd_action_re[rd_action_re["가입월"].isin(target_3m)]
    else:
        df_3m = df_action_su
        rd_3m = rd_action_re

    # 카드 1 계산 (INSTA_첫주문쿠폰의 30일 첫 주문 전환율)
    insta_su_df = df_3m[df_3m["가입채널"] == "INSTA_첫주문쿠폰"]
    if not insta_su_df.empty:
        t_sum = insta_su_df[["가입자", "첫주문30일"]].sum()
        su_val = t_sum["가입자"]
        ord_val = t_sum["첫주문30일"]
        metric1_val = f"{rate(ord_val, su_val):.1f}%" if su_val > 0 else "데이터 없음"
    else:
        metric1_val = "데이터 없음"

    # 카드 2 계산 (INSTA_첫주문쿠폰의 30일 재주문율)
    insta_re_df = rd_3m[rd_3m["가입채널"] == "INSTA_첫주문쿠폰"]
    if not insta_re_df.empty:
        tr_sum = insta_re_df[["첫주문고객", "재주문30일"]].sum()
        cust_val = tr_sum["첫주문고객"]
        re_val = tr_sum["재주문30일"]
        metric2_val = f"{rate(re_val, cust_val):.1f}%" if cust_val > 0 else "데이터 없음"
    else:
        metric2_val = "데이터 없음"

    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("**카드 1 · INSTA 첫 주문**")
            st.markdown("- 문제: INSTA_첫주문쿠폰 가입자의 30일 첫 주문 전환율 55.6% (다른 채널 75.1%)")
            st.markdown("- 근거: 식당 조회 → 장바구니 72.4% vs 88.3% · 채널을 연 2026년 1월부터 매달 47.9–63.0%")
            st.markdown("- 성격: 처음부터 그런 구조 (Android 56.8% · iOS 54.2%로 플랫폼과 무관)")
            st.markdown("- 액션: 실험: INSTA 가입자 일부에게 첫 화면 추천 식당과 쿠폰 사용 조건을 바꿔 식당 조회 → 장바구니 전환율 비교")
            st.markdown("- 우선순위: 영향 큼 · 실행 쉬움 → 실험부터")
            st.metric("현재 30일 첫 주문 전환율", metric1_val)
            st.caption("대시보드에서: 탐색 탭 · 비교 기준 가입채널 · 드릴다운 INSTA_첫주문쿠폰")

    with col2:
        with st.container(border=True):
            st.markdown("**카드 2 · INSTA 재주문**")
            st.markdown("- 문제: INSTA 가입자의 30일 재주문율 44.5% (다른 채널 72.6–77.3%)")
            st.markdown("- 근거: 첫 주문 고객 456명 중 203명만 30일 안에 다시 주문")
            st.markdown("- 성격: 처음부터 그런 구조")
            st.markdown("- 액션: 실험: INSTA 첫 주문 고객 일부에게 두 번째 주문 혜택을 주고 30일 재주문율 비교")
            st.markdown("- 우선순위: 효과 불확실 · 실행 쉬움 → 실험부터")
            st.metric("현재 30일 재주문율", metric2_val)
            st.caption("대시보드에서: 개요 탭 ③ 가입 채널별 30일 재주문율")
