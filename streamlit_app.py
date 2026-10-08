"""
7주차 프로젝트 — 시작 코드 (예제본: 신규 권역 성장 기회)
5주차 설계서 예제본의 쿼리를 SQLite로 바꾸고, 6주차 리포트의 KPI 카드 3개 · 차트 3장을
필터에 반응하도록 옮겨 둔 코드입니다. 탭 3개(개요 · 탐색 · 액션) 뼈대가 들어 있습니다.
- ✏️ 표시: 내 5주차 · 6주차 결과물로 바꿀 곳
- 📌 자리 ①~④: Gemini에게 받은 블록을 붙여 넣을 곳 (받은 블록의 첫 줄은 맨 앞에 빈칸 없이)
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
def get_db():                              # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events · odr을 만듦 (처음 한 번만)
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

# 고객별 가입일 · 가입 채널 · 플랫폼 (가입 이벤트 기준) — 두 쿼리가 같이 씀
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

# ✏️ 가입월 × 가입 채널 × 플랫폼별 가입 후 30일 퍼널 (예제본 Q1 · Q3)
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

# ✏️ 가입월 × 가입 채널 × 플랫폼별 30일 재주문 (예제본 Q2, 분모가 첫 주문 고객이라 표를 따로 만듦)
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

# 📌 자리 ① — AI 해설: Gemini가 준 AI_NOTES = { … } 로 이 줄을 바꿔 넣기
AI_NOTES = {
    "전체": "전체 가입자 2,774명의 30일 첫 주문 전환율은 69.9%이며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 84.1%다. 전체 기간 동안 안정적인 전환율을 보이나 2026년 1월부터 일부 채널 유입 변화로 전체 수치가 변동된 것으로 보인다.",
    "Android": "안드로이드 플랫폼 가입자 1,502명의 30일 첫 주문 전환율은 69.2%로 전체 평균과 유사하며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 83.8%다. iOS 대비 가입자 규모는 크나 30일 첫 주문 전환율과 30일 재주문율이 소폭 낮게 나타나 운영체제별 사용자 성향 차이가 있을 것으로 보인다.",
    "iOS": "아이오아이(iOS) 플랫폼 가입자 1,272명의 30일 첫 주문 전환율은 70.7%로 전체 평균보다 약간 높으며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 84.5%다. 안드로이드에 비해 가입자 수는 적지만 첫 주문 전환율과 30일 재주문율이 더 높게 나타나 플랫폼별 이용 행태에 차이가 있는 것으로 보인다.",
    "organic": "오가닉(organic) 채널 가입자 847명의 30일 첫 주문 전환율은 75.2%로 전체 평균 대비 높으며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 88.6%다. 광고 등 외부 유입 채널에 비해 초기 퍼널 단계와 30일 재주문율(73.5%)이 우수해 충성도가 높은 유저들로 구성된 것으로 보인다.",
    "INSTA_첫주문쿠폰": "인스타 첫주문쿠폰 채널 가입자 739명의 30일 첫 주문 전환율은 55.6%로 전체 집단 중 가장 낮으며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 72.4%다. 2026-01 가입월부터 처음 나타나며 전체 전환율 하락을 주도하였고 30일 재주문율도 44.5%로 낮아 유입 고객의 질적 차이가 있을 것으로 보인다.",
    "NAVER_검색광고": "네이버 검색광고 채널 가입자 517명의 30일 첫 주문 전환율은 76.4%로 전체 평균을 상회하며 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 87.7%다. 오가닉과 함께 상위권의 전환 성능을 보이며 30일 재주문율도 72.6%로 높아 검색 의도가 명확한 유저들이 유입된 것으로 보인다.",
    "GOOGLE_앱설치": "구글 앱설치 채널 가입자 398명으로 300명을 초과하며 30일 첫 주문 전환율은 73.6%이고 가장 낮은 단계 전환율은 유일하게 장바구니에서 결제시작으로 이어지는 88.0%다. 타 채널과 달리 식당조회 단계 이후 장바구니에서 결제로 넘어갈 때의 이탈이 상대적으로 두드러져 해당 단계의 UI나 프로세스 점검이 필요하다.",
    "친구초대": "친구초대 채널 가입자 273명으로 300명 미만이며 30일 첫 주문 전환율은 74.4%이고 가장 낮은 단계 전환율은 식당조회에서 장바구니로 이어지는 87.1%다. 집단 크기가 작음에도 불구하고 30일 재주문율이 77.3%로 모든 집단 중 가장 높아 지인 추천을 통한 유저의 락인 효과가 매우 높을 것으로 보인다."
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

with tab_overview:
    st.caption("이 탭에서 볼 수 있는 것: 핵심 숫자와 그 숫자를 읽는 법, 6주차 리포트의 차트 3장 (필터 적용)")

    # 3-1. KPI 카드 — ✏️ 5주차 지표 3개
    t = f[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum()
    tr = rf[["첫주문고객", "재주문30일"]].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("30일 첫 주문 전환율", f"{rate(t['첫주문30일'], t['가입자']):.1f}%", border=True, help="가입 후 30일 안에 첫 주문한 가입자 ÷ 가입자")
    c2.metric("식당 조회 → 장바구니 전환율", f"{rate(t['장바구니'], t['식당조회']):.1f}%", border=True, help="장바구니에 담은 가입자 ÷ 식당을 조회한 가입자")
    c3.metric("30일 재주문율", f"{rate(tr['재주문30일'], tr['첫주문고객']):.1f}%", border=True, help="첫 주문 후 30일 안에 다시 주문한 고객 ÷ 첫 주문 고객")

    # 📏 지금 숫자 읽기 상자 추가
    with st.container(border=True):
        st.markdown("**📏 지금 숫자 읽기**")

        # 고유한 월 목록 정렬
        sorted_months = sorted(f["가입월"].unique())
        
        # 3개월 미만 체크 함수/로직
        if len(sorted_months) < 3:
            msg_order = "비교하려면 선택 기간을 3개월 이상 골라 주세요"
            msg_cart = "비교하려면 선택 기간을 3개월 이상 골라 주세요"
            sentence1 = f"- **30일 첫 주문 전환율**: {msg_order}"
            sentence2 = f"- **식당 조회 → 장바구니 전환율**: {msg_cart}"
        else:
            # 1. 이번 값: f의 마지막 3개월 합계로 계산한 전환율
            last_3_months = sorted_months[-3:]
            f_last3 = f[f["가입월"].isin(last_3_months)]
            t_last3 = f_last3[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum()
            
            cur_order_rate = rate(t_last3["첫주문30일"], t_last3["가입자"])
            cur_cart_rate = rate(t_last3["장바구니"], t_last3["식당조회"])
            
            period_str = f"{last_3_months[0]}월부터 3개월"

            # 2. 평소 범위: g에서 기준 기간(base_start ~ base_end)에 해당하는 월별 전환율의 최솟값 ~ 최댓값
            base_f = g[(g["가입월"] >= base_start) & (g["가입월"] <= base_end)]
            base_months_unique = sorted(base_f["가입월"].unique())

            if len(base_months_unique) < 3:
                sentence1 = "- **30일 첫 주문 전환율**: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
                sentence2 = "- **식당 조회 → 장바구니 전환율**: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
            else:
                # 월별 집계
                monthly_base = base_f.groupby("가입월")[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum().reset_index()
                
                order_rates = []
                cart_rates = []
                for _, row in monthly_base.iterrows():
                    # 분모가 0인 달은 평소 범위 계산에서 빼기
                    if row["가입자"] > 0:
                        order_rates.append(row["첫주문30일"] / row["가입자"] * 100)
                    if row["식당조회"] > 0:
                        cart_rates.append(row["장바구니"] / row["식당조회"] * 100)

                if not order_rates or not cart_rates:
                    sentence1 = "- **30일 첫 주문 전환율**: 기준 기간에 유효한 데이터가 부족합니다."
                    sentence2 = "- **식당 조회 → 장바구니 전환율**: 기준 기간에 유효한 데이터가 부족합니다."
                else:
                    min_order, max_order = min(order_rates), max(order_rates)
                    min_cart, max_cart = min(cart_rates), max(cart_rates)

                    range_order_str = f"{min_order:.1f}–{max_order:.1f}%"
                    range_cart_str = f"{min_cart:.1f}–{max_cart:.1f}%"

                    # 30일 첫 주문 전환율 문장 생성
                    if cur_order_rate < min_order:
                        diff = min_order - cur_order_rate
                        order_eval = f"평소 범위({range_order_str})보다 {diff:.1f}%p 낮습니다."
                    elif cur_order_rate > max_order:
                        diff = cur_order_rate - max_order
                        order_eval = f"평소 범위({range_order_str})보다 {diff:.1f}%p 높습니다."
                    else:
                        order_eval = f"평소 범위({range_order_str}) 내에 있습니다."

                    sentence1 = f"- **30일 첫 주문 전환율**: {period_str} 동안 {cur_order_rate:.1f}%로, 평소 범위({range_order_str})와 비교해 {order_eval}"

                    # 식당 조회 -> 장바구니 전환율 문장 생성
                    if cur_cart_rate < min_cart:
                        diff = min_cart - cur_cart_rate
                        cart_eval = f"평소 범위({range_cart_str})보다 {diff:.1f}%p 낮습니다."
                    elif cur_cart_rate > max_cart:
                        diff = cur_cart_rate - max_cart
                        cart_eval = f"평소 범위({range_cart_str})보다 {diff:.1f}%p 높습니다."
                    else:
                        cart_eval = f"평소 범위({range_cart_str}) 내에 있습니다."

                    sentence2 = f"- **식당 조회 → 장바구니 전환율**: {period_str} 동안 {cur_cart_rate:.1f}%로, 평소 범위({range_cart_str})와 비교해 {cart_eval}"

        st.markdown(sentence1)
        st.markdown(sentence2)
        st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {base_start} ~ {base_end} (월별 값)")

        with st.expander("🤖 AI 해설 · 전체", expanded=False):
            st.write(AI_NOTES.get("전체", "아직 해설이 없습니다."))
            st.caption(AI_SOURCE)

# 📌 자리 ② — 규칙 문장 블록 (with tab_overview: 로 시작하는 블록을 여기에)

with tab_overview:
    st.divider()

    # 3-2. 차트 — ✏️ 6주차 차트 ① 문제 · ② 원인 · ③ 제안
    left, right = st.columns(2, border=True)

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
    fig3.update_traces(marker_color=[ACCENT if c == "INSTA_첫주문쿠폰" else GRAY for c in rc["가입채널"]])
    fig3.update_xaxes(visible=False)
    st.plotly_chart(fig3, width="stretch")

    # AI 해설을 만들 때 Gemini에 올릴 표 (필터와 관계없이 전체)
    with st.expander("📥 AI 해설용 데이터 내려받기"):
        st.download_button("가입 후 30일 퍼널 (가입월 × 가입 채널 × 플랫폼)",
                           df.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_퍼널.csv")
        st.download_button("30일 재주문 (가입월 × 가입 채널 × 플랫폼)",
                           rd.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_재주문.csv")

with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교와 드릴다운 — 어디서, 언제부터인가")

# 📌 자리 ③ — 탐색 블록들 (with tab_explore: 로 시작하는 블록을 받은 순서대로 여기에)

with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교와 드릴다운 — 어디서, 언제부터인가")
    st.subheader("집단 비교")

    col1, col2 = st.columns([1, 3])
    with col1:
        group_by_option = st.radio("비교 기준", ["가입채널", "플랫폼"], horizontal=True)

    # 1. 집단별 퍼널 단계 합계 계산
    grouped = f.groupby(group_by_option)[["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]].sum().reset_index()

    # 2. 작은 집단 필터링 처리
    if hide_small:
        small_groups = grouped[grouped["가입자"] < SMALL][group_by_option].tolist()
        filtered_grouped = grouped[grouped["가입자"] >= SMALL]
        if small_groups:
            st.caption(f"제외한 집단: {', '.join(small_groups)} (가입자 {SMALL}명 미만)")
    else:
        filtered_grouped = grouped

    # 남은 집단 중 SMALL명 미만인 집단이 있는지 확인 (경고용)
    remaining_small = filtered_grouped[filtered_grouped["가입자"] < SMALL][group_by_option].tolist()

    if filtered_grouped.empty:
        st.warning("조건을 만족하는 집단이 없습니다.")
    else:
        # 데이터프레임 melt 준비 (퍼널 및 단계 전환용)
        # 퍼널용 데이터 (누적 전환율 계산)
        funnel_df_list = []
        for _, row in filtered_grouped.iterrows():
            g_name = row[group_by_option]
            base_val = row["가입자"]
            if base_val == 0:
                continue
            steps = [
                ("가입자", row["가입자"], 100.0),
                ("식당조회", row["식당조회"], rate(row["식당조회"], base_val)),
                ("장바구니", row["장바구니"], rate(row["장바구니"], base_val)),
                ("결제시작", row["결제시작"], rate(row["결제시작"], base_val)),
                ("첫주문30일", row["첫주문30일"], rate(row["첫주문30일"], base_val)),
            ]
            for step_name, count_val, rate_val in steps:
                funnel_df_list.append({
                    group_by_option: g_name,
                    "단계": step_name,
                    "누적전환율": round(rate_val, 1),
                    "사람수": count_val
                })
        melted_funnel = pd.DataFrame(funnel_df_list)

        # 단계 전환율 데이터 준비 (직전 단계 대비 %)
        trans_df_list = []
        for _, row in filtered_grouped.iterrows():
            g_name = row[group_by_option]
            u_gaip = row["가입자"]
            u_shik = row["식당조회"]
            u_jang = row["장바구니"]
            u_gyul = row["결제시작"]
            u_jum = row["첫주문30일"]

            steps_trans = [
                ("가입자 → 식당조회", u_shik, u_gaip),
                ("식당조회 → 장바구니", u_jang, u_shik),
                ("장바구니 → 결제시작", u_gyul, u_jang),
                ("결제시작 → 첫주문30일", u_jum, u_gyul),
            ]
            for step_name, cur_val, prev_val in steps_trans:
                r_val = rate(cur_val, prev_val)
                trans_df_list.append({
                    group_by_option: g_name,
                    "전환단계": step_name,
                    "단계전환율": round(r_val, 1),
                    "직전단계사람수": prev_val
                })
        melted_trans = pd.DataFrame(trans_df_list)

        left_chart, right_chart = st.columns(2)

        # 왼쪽: 누적 전환율 퍼널 차트
        fig_funnel = px.funnel(
            melted_funnel,
            x="누적전환율",
            y="단계",
            color=group_by_option,
            hover_data={"사람수": True, "누적전환율": True},
            labels={"누적전환율": "누적 전환율(%)", "단계": "퍼널 단계", group_by_option: "집단"},
            title="집단별 누적 전환율 퍼널"
        )
        left_chart.plotly_chart(fig_funnel, width="stretch")

        # 오른쪽: 단계 전환율 막대 차트 (barmode="group")
        fig_bar = px.bar(
            melted_trans,
            x="전환단계",
            y="단계전환율",
            color=group_by_option,
            barmode="group",
            text="단계전환율",
            hover_data={"직전단계사람수": True, "단계전환율": True},
            labels={"단계전환율": "단계 전환율(%)", "전환단계": "전환 단계", group_by_option: "집단", "직전단계사람수": "직전 단계 사람 수(명)"},
            title="집단별 단계 전환율 비교"
        )
        fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        right_chart.plotly_chart(fig_bar, width="stretch")

        if remaining_small:
            st.caption(f"⚠️ 주의: 남은 집단 중 {', '.join(remaining_small)}은(는) 가입자가 {SMALL}명 미만으로 값이 크게 흔들릴 수 있습니다.")

    st.divider()
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    available_groups = filtered_grouped[group_by_option].tolist()
    if not available_groups:
        st.warning("선택 가능한 집단이 없습니다.")
    else:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            selected_group = st.selectbox("자세히 볼 집단", available_groups)
        with d_col2:
            selected_step = st.selectbox(
                "단계",
                ["가입 → 30일 첫 주문", "가입 → 식당조회", "식당조회 → 장바구니", "장바구니 → 결제시작", "결제시작 → 30일 첫 주문"]
            )

        other_axis = "플랫폼" if group_by_option == "가입채널" else "가입채널"

        # 차트 ① 데이터 처리
        sub_f = f[f[group_by_option] == selected_group]
        monthly_group_sub = sub_f.groupby(["가입월", other_axis])[["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]].sum().reset_index()

        chart1_data = []
        for (month, other_val), group_data in monthly_group_sub.groupby(["가입월", other_axis]):
            g_cnt = group_data["가입자"].sum()
            s_cnt = group_data["식당조회"].sum()
            b_cnt = group_data["장바구니"].sum()
            c_cnt = group_data["결제시작"].sum()
            o_cnt = group_data["첫주문30일"].sum()

            if selected_step == "가입 → 30일 첫 주문":
                prev_val, cur_val = g_cnt, o_cnt
            elif selected_step == "가입 → 식당조회":
                prev_val, cur_val = g_cnt, s_cnt
            elif selected_step == "식당조회 → 장바구니":
                prev_val, cur_val = s_cnt, b_cnt
            elif selected_step == "장바구니 → 결제시작":
                prev_val, cur_val = b_cnt, c_cnt
            elif selected_step == "결제시작 → 30일 첫 주문":
                prev_val, cur_val = c_cnt, o_cnt
            else:
                prev_val, cur_val = 0, 0

            # 직전 단계 사람 수가 0이면 빈 값(None) 처리
            rate_val = round(cur_val / prev_val * 100, 1) if prev_val > 0 else None

            chart1_data.append({
                "가입월": month,
                other_axis: other_val,
                "전환율": rate_val,
                "직전단계사람수": prev_val
            })

        df_chart1 = pd.DataFrame(chart1_data)

        fig_drill1 = px.line(
            df_chart1,
            x="가입월",
            y="전환율",
            color=other_axis,
            markers=True,
            hover_data=["직전단계사람수"],
            labels={"가입월": "가입월", "전환율": "전환율(%)", other_axis: other_axis, "직전단계사람수": "직전 단계 사람 수(명)"},
            title=f"① {selected_group}의 가입월별 {selected_step} 전환율 — {other_axis}별로 쪼개 보기"
        )
        fig_drill1.update_layout(xaxis_title="")
        st.plotly_chart(fig_drill1, width="stretch")
        st.caption("모든 갈래가 함께 움직였다면, 그 축은 원인이 아닙니다.")

        # 차트 ② 데이터 처리 (가입월별 가입자 수 막대 쌓기: 고른 집단 vs 그 외)
        df_all_monthly = f.groupby("가입월")["가입자"].sum().reset_index()
        df_sel_monthly = sub_f.groupby("가입월")["가입자"].sum().reset_index()

        merged_bar = pd.merge(df_all_monthly, df_sel_monthly, on="가입월", suffixes=("_전체", "_선택"), how="left").fillna(0)
        merged_bar["그외"] = merged_bar["가입자_전체"] - merged_bar["가입자_선택"]

        chart2_melted = []
        for _, row in merged_bar.iterrows():
            chart2_melted.append({
                "가입월": row["가입월"],
                "집단구분": selected_group,
                "가입자수": row["가입자_선택"]
            })
            chart2_melted.append({
                "가입월": row["가입월"],
                "집단구분": "그 외",
                "가입자수": row["그외"]
            })
        df_chart2 = pd.DataFrame(chart2_melted)

        # 색상 매핑: 고른 집단 진한 남색, 그 외 회색
        color_map = {selected_group: ACCENT, "그 외": "#d3d3d3"}

        fig_drill2 = px.bar(
            df_chart2,
            x="가입월",
            y="가입자수",
            color="집단구분",
            barmode="stack",
            color_discrete_map=color_map,
            labels={"가입월": "가입월", "가입자수": "가입자 수(명)", "집단구분": "집단"},
            title=f"② 가입월별 가입자 수 구성 ({selected_group} vs 그 외)"
        )
        fig_drill2.update_layout(xaxis_title="")
        st.plotly_chart(fig_drill2, width="stretch")
        st.caption("전체 전환율이 움직인 시점에 이 집단의 비중이 함께 바뀌었다면 구성 변화가 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

        # AI 해설 익스팬더
        with st.expander(f"🤖 AI 해설 · {selected_group}", expanded=False):
            st.write(AI_NOTES.get(selected_group, "이 집단의 해설은 아직 없습니다."))
            st.caption(AI_SOURCE)

# 📌 자리 ④ — 액션 탭: 아래 with tab_action: 줄부터 파일 끝까지를 받은 블록으로 바꾸기
with tab_action:
    st.caption("측정 KPI의 현재 값은 선택한 기간의 마지막 3개월로 계산합니다")

    # 사이드바 가입월 기간(start ~ end)만 적용한 필터 (가입 채널 · 플랫폼 필터는 무시)
    df_action = df[(df["가입월"] >= start) & (df["가입월"] <= end)]
    rd_action = rd[(rd["가입월"] >= start) & (rd["가입월"] <= end)]

    # 선택 기간의 마지막 3개월 추출
    action_months = sorted(df_action["가입월"].unique())
    if len(action_months) >= 3:
        target_months = action_months[-3:]
        df_last3 = df_action[df_action["가입월"].isin(target_months)]
        rd_last3 = rd_action[rd_action["가입월"].isin(target_months)]
    else:
        df_last3 = df_action
        rd_last3 = rd_action

    # 카드 1 데이터 (INSTA_첫주문쿠폰)
    insta_df = df_last3[df_last3["가입채널"] == "INSTA_첫주문쿠폰"]
    if not insta_df.empty:
        t_insta = insta_df[["가입자", "첫주문30일"]].sum()
        val_card1 = f"{rate(t_insta['첫주문30일'], t_insta['가입자']):.1f}%"
    else:
        val_card1 = "데이터 없음"

    # 카드 2 데이터 (INSTA_첫주문쿠폰)
    insta_rd = rd_last3[rd_last3["가입채널"] == "INSTA_첫주문쿠폰"]
    if not insta_rd.empty:
        tr_insta = insta_rd[["첫주문고객", "재주문30일"]].sum()
        val_card2 = f"{rate(tr_insta['재주문30일'], tr_insta['첫주문고객']):.1f}%"
    else:
        val_card2 = "데이터 없음"

    col_action1, col_action2 = st.columns(2)

    with col_action1:
        with st.container(border=True):
            st.markdown("**카드 1 · INSTA 첫 주문**")
            st.markdown("- 문제: INSTA_첫주문쿠폰 가입자의 30일 첫 주문 전환율 55.6% (다른 채널 75.1%)")
            st.markdown("- 근거: 식당 조회 → 장바구니 72.4% vs 88.3% · 채널을 연 2026년 1월부터 매달 47.9–63.0%")
            st.markdown("- 성격: 처음부터 그런 구조 (Android 56.8% · iOS 54.2%로 플랫폼과 무관)")
            st.markdown("- 액션: 실험: INSTA 가입자 일부에게 첫 화면 추천 식당과 쿠폰 사용 조건을 바꿔 식당 조회 → 장바구니 전환율 비교")
            st.markdown("- 우선순위: 영향 큼 · 실행 쉬움 → 실험부터")
            st.metric("30일 첫 주문 전환율 (INSTA_첫주문쿠폰)", val_card1)
            st.caption("대시보드에서: 탐색 탭 · 비교 기준 가입채널 · 드릴다운 INSTA_첫주문쿠폰")

    with col_action2:
        with st.container(border=True):
            st.markdown("**카드 2 · INSTA 재주문**")
            st.markdown("- 문제: INSTA 가입자의 30일 재주문율 44.5% (다른 채널 72.6–77.3%)")
            st.markdown("- 근거: 첫 주문 고객 456명 중 203명만 30일 안에 다시 주문")
            st.markdown("- 성격: 처음부터 그런 구조")
            st.markdown("- 액션: 실험: INSTA 첫 주문 고객 일부에게 두 번째 주문 혜택을 주고 30일 재주문율 비교")
            st.markdown("- 우선순위: 효과 불확실 · 실행 쉬움 → 실험부터")
            st.metric("30일 재주문율 (INSTA_첫주문쿠폰)", val_card2)
            st.caption("대시보드에서: 개요 탭 ③ 가입 채널별 30일 재주문율")
