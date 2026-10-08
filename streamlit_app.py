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
    "전체": "전체 가입자 2774명의 30일 첫 주문 전환율은 69.9%이며 가장 낮은 단계 전환율은 84.1%인 식당조회에서 장바구니로의 단계다. 개별 채널이나 플랫폼 지표와 비교했을 때 전체 평균 수준의 퍼널 흐름을 보여준다. 2026년 1월부터 전체 30일 첫 주문 전환율이 67.8%로 이전 기간 대비 낮아진 흐름이 확인된다.",
    "Android": "안드로이드 플랫폼의 가입자는 1502명으로 30일 첫 주문 전환율은 69.2%이고 가장 낮은 단계 전환율은 83.8%인 식당조회에서 장바구니 단계다. 전체 집단이나 iOS 플랫폼의 70.7%에 비해서는 첫 주문 전환율이 소폭 낮은 편이다. 안드로이드 환경에서의 특정 유입 패턴이나 퍼널 이탈 원인에 대한 추가적인 확인이 필요하다.",
    "iOS": "아이오에스 플랫폼의 가입자는 1272명으로 30일 첫 주문 전환율은 70.7%이며 가장 낮은 단계 전환율은 84.5%인 식당조회에서 장바구니 단계다. 안드로이드 플랫폼의 69.2%나 전체 평균인 69.9%에 비해서는 첫 주문 전환율이 약간 높게 나타났다. 기기 사용자들의 서비스 이용 성향 차이가 이러한 전환율 격차에 영향을 준 것으로 보인다.",
    "organic": "오가닉 채널의 가입자는 847명이며 30일 첫 주문 전환율은 75.2%로 전체 대비 높고 가장 낮은 단계 전환율은 88.6%인 식당조회에서 장바구니 단계다. 광고나 쿠폰을 통한 다른 유입 집단에 비해 전반적인 퍼널 전환 효율이 우수한 편이다. 자발적인 유입 특성상 서비스에 대한 관여도가 높아 전환율이 높게 나타난 것으로 보인다.",
    "INSTA_첫주문쿠폰": "인스타 첫주문쿠폰 채널의 가입자는 739명이며 30일 첫 주문 전환율은 55.6%로 전체 대비 크게 낮고 가장 낮은 단계 전환율은 72.4%인 식당조회에서 장바구니 단계다. 2026년 1월부터 처음 나타나기 시작했으며 이 채널이 포함되면서 2026년 1월 이후 전체 첫 주문 전환율이 하락했다. 쿠폰 혜택으로 유입된 사용자의 실질적인 구매 의도가 낮거나 허수 가입이 많았을 가능성에 대한 확인이 필요하다.",
    "NAVER_검색광고": "네이버 검색광고 채널의 가입자는 517명이며 30일 첫 주문 전환율은 76.4%로 전체 대비 높고 가장 낮은 단계 전환율은 87.7%인 식당조회에서 장바구니 단계다. 다른 주요 유입 채널들과 비교했을 때 첫 주문 전환율과 재주문율 모두 상위권에 속한다. 검색 광고를 통해 유입된 사용자의 목적성이 뚜렷하여 구매 전환으로 원활히 이어진 것으로 보인다.",
    "GOOGLE_앱설치": "구글 앱설치 채널의 가입자는 398명이며 30일 첫 주문 전환율은 73.6%이고 다른 집단과 달리 가장 낮은 단계 전환율이 88.0%인 장바구니에서 결제시작 단계다. 다른 채널들이 모두 식당조회에서 장바구니 단계를 최저로 기록한 것과 차이가 있다. 앱 설치 직후 결제 단계로 진입하는 과정에서 특정 UI나 허들이 작용했을 가능성에 대한 확인이 필요하다.",
    "친구초대": "친구초대 채널의 가입자는 273명으로 300명 미만이며 30일 첫 주문 전환율은 74.4%이고 가장 낮은 단계 전환율은 87.1%인 식당조회에서 장바구니 단계다. 집단 크기가 작음에도 불구하고 30일 재주문율은 77.3%로 분석된 대상 중 가장 높게 나타났다. 지인을 통해 가입한 특성상 서비스 신뢰도가 높아 재주문으로 이어지는 비율이 높았던 것으로 보인다."
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

    # ------------------------------------------------------------
    # 지금 숫자 읽기
    # ------------------------------------------------------------
    with st.container(border=True):
        st.markdown("**📏 지금 숫자 읽기**")

        # 대상 지표 정의 (이름, 분자, 분모)
        metrics_to_read = [
            ("30일 첫 주문 전환율", "첫주문30일", "가입자"),
            ("식당 조회 → 장바구니 전환율", "장바구니", "식당조회")
        ]

        # f 데이터의 가입월 정렬 목록 추출
        sorted_f_months = sorted(f["가입월"].unique())
        n_f_months = len(sorted_f_months)

        # g 데이터에서 기준 기간(base_start ~ base_end) 데이터 필터링
        g_base = g[(g["가입월"] >= base_start) & (g["가입월"] <= base_end)]
        base_months_unique = sorted(g_base["가입월"].unique())

        bullet_lines = []

        if n_f_months < 3:
            bullet_lines.append("비교하려면 선택 기간을 3개월 이상 골라 주세요")
        elif len(base_months_unique) < 3:
            bullet_lines.append("기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요")
        else:
            # 이번 값: f의 마지막 3개월 합계로 계산
            last_3_months = sorted_f_months[-3:]
            f_last3 = f[f["가입월"].isin(last_3_months)]
            target_start_month = last_3_months[0]

            # 평소 범위 계산: g_base에서 가입월별로 분자/분모를 먼저 더한 뒤 월별 전환율 산출 후 min~max
            base_monthly = g_base.groupby("가입월")[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum().reset_index()

            for name, num_col, den_col in metrics_to_read:
                # 이번 값 계산
                t_num = f_last3[num_col].sum()
                t_den = f_last3[den_col].sum()
                val_current = (t_num / t_den * 100) if t_den > 0 else 0.0

                # 평소 범위 월별 계산
                monthly_rates = []
                for _, row in base_monthly.iterrows():
                    d_val = row[den_col]
                    n_val = row[num_col]
                    if d_val > 0:
                        monthly_rates.append(n_val / d_val * 100)

                if monthly_rates:
                    min_rate = min(monthly_rates)
                    max_rate = max(monthly_rates)
                    
                    diff = val_current - ((min_rate + max_rate) / 2) # 비교용 (낮으면/높으면 판단)
                    # 표현식 결정
                    if val_current < min_rate:
                        diff_val = min_rate - val_current
                        diff_str = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 낮습니다"
                    elif val_current > max_rate:
                        diff_val = val_current - max_rate
                        diff_str = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 높습니다"
                    else:
                        diff_str = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%) 안에 있습니다"

                    bullet_lines.append(f"{target_start_month} 가입월부터 3개월 {name}은 {val_current:.1f}%로, {diff_str}")
                else:
                    bullet_lines.append(f"{target_start_month} 가입월부터 3개월 {name}은 {val_current:.1f}%이나 평소 범위 데이터가 부족합니다.")

        for line in bullet_lines:
            st.markdown(f"- {line}")

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

    st.subheader("집단 비교")
    comp_by = st.radio("비교 기준", ["가입채널", "플랫폼"], horizontal=True, key="비교기준_radio")

    # 선택한 기준별로 5단계 지표 집계
    cols_to_sum = ["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]
    df_comp = f.groupby(comp_by)[cols_to_sum].sum().reset_index()

    # 작은 집단 제외 처리
    small_groups = []
    if hide_small:
        small_groups = df_comp[df_comp["가입자"] < SMALL][comp_by].tolist()
        if small_groups:
            st.caption(f"제외한 집단: {', '.join(map(str, small_groups))} (가입자 {SMALL}명 미만)")
        df_comp = df_comp[df_comp["가입자"] >= SMALL]

    if df_comp.empty:
        st.warning("조건에 맞는 집단이 없습니다. 필터를 조정해 주세요.")
    else:
        # 남은 집단 중 가입자 < SMALL인 집단이 있는지 확인 (혹시 모를 경우 대비)
        warning_groups = df_comp[df_comp["가입자"] < SMALL][comp_by].tolist()
        if warning_groups:
            st.caption(f"주의: {', '.join(map(str, warning_groups))} 집단은 가입자가 {SMALL}명 미만으로 값이 크게 흔들릴 수 있습니다.")

        # 데이터 변환 (퍼널 및 단계 전환율 계산용)
        funnel_rows = []
        step_rows = []

        for _, row in df_comp.iterrows():
            g_name = row[comp_by]
            base_n = row["가입자"]
            su_n = row["식당조회"]
            cart_n = row["장바구니"]
            chk_n = row["결제시작"]
            ord_n = row["첫주문30일"]

            # 누적 전환율 (%)
            funnel_rows.extend([
                {comp_by: g_name, "단계": "가입자", "누적전환율": 100.0, "인원수": base_n},
                {comp_by: g_name, "단계": "식당조회", "누적전환율": rate(su_n, base_n), "인원수": su_n},
                {comp_by: g_name, "단계": "장바구니", "누적전환율": rate(cart_n, base_n), "인원수": cart_n},
                {comp_by: g_name, "단계": "결제시작", "누적전환율": rate(chk_n, base_n), "인원수": chk_n},
                {comp_by: g_name, "단계": "첫주문30일", "누적전환율": rate(ord_n, base_n), "인원수": ord_n},
            ])

            # 단계별 전환율 (%) 및 직전 단계 사람 수
            step_rows.extend([
                {comp_by: g_name, "단계": "식당조회 (가입자 대비)", "전환율": rate(su_n, base_n), "직전인원": base_n},
                {comp_by: g_name, "단계": "장바구니 (식당조회 대비)", "전환율": rate(cart_n, su_n), "직전인원": su_n},
                {comp_by: g_name, "단계": "결제시작 (장바구니 대비)", "전환율": rate(chk_n, cart_n), "직전인원": cart_n},
                {comp_by: g_name, "단계": "첫주문30일 (결제시작 대비)", "전환율": rate(ord_n, chk_n), "직전인원": chk_n},
            ])

        df_funnel_plot = pd.DataFrame(funnel_rows)
        df_step_plot = pd.DataFrame(step_rows)

        col_left, col_right = st.columns(2)

        with col_left:
            fig_f = px.funnel(
                df_funnel_plot,
                x="누적전환율",
                y="단계",
                color=comp_by,
                labels={"누적전환율": "누적 전환율(%)", "단계": "퍼널 단계", comp_by: "집단", "인원수": "인원수(명)"},
                title="집단별 누적 전환율 퍼널"
            )
            col_left.plotly_chart(fig_f, width="stretch")

        with col_right:
            fig_s = px.bar(
                df_step_plot,
                x="단계",
                y="전환율",
                color=comp_by,
                barmode="group",
                text_auto=".1f",
                hover_data={"직전인원": True, "전환율": ":.1f"},
                labels={"전환율": "단계 전환율(%)", "단계": "퍼널 단계", comp_by: "집단", "직전인원": "직전 단계 사람 수(명)"},
                title="집단별 단계 전환율 비교"
            )
            fig_s.update_layout(xaxis_title="", yaxis_title="단계 전환율(%)")
            col_right.plotly_chart(fig_s, width="stretch")

    st.divider()

    # ------------------------------------------------------------
    # 드릴다운: 언제부터, 무엇 때문일까
    # ------------------------------------------------------------
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    available_groups = df_comp[comp_by].tolist() if not df_comp.empty else []
    
    if not available_groups:
        st.warning("선택 가능한 집단이 없습니다.")
    else:
        drill_col1, drill_col2 = st.columns(2)
        with drill_col1:
            selected_group = st.selectbox("자세히 볼 집단", available_groups, key="drill_group_sel")
        with drill_col2:
            step_options = {
                "가입 → 30일 첫 주문": ("가입자", "첫주문30일"),
                "가입 → 식당조회": ("가입자", "식당조회"),
                "식당조회 → 장바구니": ("식당조회", "장바구니"),
                "장바구니 → 결제시작": ("장바구니", "결제시작"),
                "결제시작 → 30일 첫 주문": ("결제시작", "첫주문30일"),
            }
            selected_step_name = st.selectbox("단계", list(step_options.keys()), key="drill_step_sel")

        den_col, num_col = step_options[selected_step_name]
        other_axis = "플랫폼" if comp_by == "가입채널" else "가입채널"

        # 차트 ① 데이터 준비
        # f 기준에서 고른 집단 행만 추출 후, 가입월 및 other_axis별로 집계
        f_group = f[f[comp_by] == selected_group]
        m_drill = f_group.groupby(["가입월", other_axis])[[den_col, num_col]].sum().reset_index()
        
        # 직전 단계 인원(den_col)이 0인 경우 전환율을 계산하지 않고 None(빈 값) 처리
        # 전환율은 뒤 단계 ÷ 앞 단계 (num_col / den_col)
        m_drill["전환율"] = m_drill.apply(
            lambda r: (r[num_col] / r[den_col] * 100) if r[den_col] > 0 else None, axis=1
        )

        fig_drill_1 = px.line(
            m_drill,
            x="가입월",
            y="전환율",
            color=other_axis,
            markers=True,
            hover_data=[den_col, num_col],
            labels={
                "가입월": "가입월",
                "전환율": "전환율(%)",
                den_col: "직전 단계 사람 수(명)",
                num_col: "해당 단계 사람 수(명)",
                other_axis: other_axis
            },
            title=f"① {selected_group}의 가입월별 {selected_step_name} 전환율 — {other_axis}별로 쪼개 보기"
        )
        fig_drill_1.update_layout(xaxis_title="")
        fig_drill_1.update_xaxes(type="category")
        st.plotly_chart(fig_drill_1, width="stretch")
        st.caption("모든 갈래가 함께 움직였다면, 그 축은 원인이 아닙니다.")

        # 차트 ② 데이터 준비
        # 가입월별 전체 f 데이터에서 고른 집단 vs 그 외 집단 분류
        f_copy = f.copy()
        f_copy["집단분류"] = f_copy[comp_by].apply(lambda x: selected_group if x == selected_group else "그 외")
        m_bar = f_copy.groupby(["가입월", "집단분류"])["가입자"].sum().reset_index()

        fig_drill_2 = px.bar(
            m_bar,
            x="가입월",
            y="가입자",
            color="집단분류",
            barmode="stack",
            color_discrete_map={selected_group: "#1f3b73", "그 외": "#cccccc"},
            labels={"가입월": "가입월", "가입자": "가입자 수(명)", "집단분류": "집단"},
            title=f"② 가입월별 가입자 수 구성 ({selected_group} vs 그 외)"
        )
        fig_drill_2.update_layout(xaxis_title="")
        fig_drill_2.update_xaxes(type="category")
        st.plotly_chart(fig_drill_2, width="stretch")
        st.caption("전체 전환율이 움직인 시점에 이 집단의 비중이 함께 바뀌었다면 구성 변화가 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

        # AI 해설 익스팬더
        with st.expander(f"🤖 AI 해설 · {selected_group}", expanded=False):
            st.write(AI_NOTES.get(selected_group, "이 집단의 해설은 아직 없습니다."))
            st.caption(AI_SOURCE)
# ===== [블록 B] 끝 =====

# ===== [블록 C] 액션 — 액션 카드 단계에서 이 줄 아래부터 파일 끝까지를 받은 블록으로 바꿈 =====
with tab_action:
    st.caption("측정 KPI의 현재 값은 선택한 기간의 마지막 3개월로 계산합니다")

    act_col1, act_col2 = st.columns(2)

    # 공통: 사이드바의 가입월 기간(start ~ end)만 적용 (채널·플랫폼 필터 무시)
    df_period = df[(df["가입월"] >= start) & (df["가입월"] <= end)]
    rd_period = rd[(rd["가입월"] >= start) & (rd["가입월"] <= end)]

    # 마지막 3개월 추출을 위한 가입월 목록
    df_months = sorted(df_period["가입월"].unique())
    rd_months = sorted(rd_period["가입월"].unique())

    df_last3_months = df_months[-3:] if len(df_months) >= 3 else df_months
    rd_last3_months = rd_months[-3:] if len(rd_months) >= 3 else rd_months

    # ------------------------------------------------------------
    # 카드 1 · INSTA 첫 주문
    # ------------------------------------------------------------
    with act_col1:
        with st.container(border=True):
            st.markdown("**카드 1 · INSTA 첫 주문**")
            st.markdown(
                "- 문제: INSTA_첫주문쿠폰 가입자의 30일 첫 주문 전환율 55.6% (다른 채널 75.1%)\n"
                "- 근거: 식당 조회 → 장바구니 72.4% vs 88.3% · 채널을 연 2026년 1월부터 매달 47.9–63.0%\n"
                "- 성격: 처음부터 그런 구조 (Android 56.8% · iOS 54.2%로 플랫폼과 무관)\n"
                "- 액션: 실험: INSTA 가입자 일부에게 첫 화면 추천 식당과 쿠폰 사용 조건을 바꿔 식당 조회 → 장바구니 전환율 비교\n"
                "- 우선순위: 영향 큼 · 실행 쉬움 → 실험부터"
            )

            # 카드 1 KPI 계산 (가입채널 == "INSTA_첫주문쿠폰", 마지막 3개월)
            c1_data = df_period[
                (df_period["가입채널"] == "INSTA_첫주문쿠폰") & (df_period["가입월"].isin(df_last3_months))
            ]
            if not c1_data.empty:
                t1_sum = c1_data[["가입자", "첫주문30일"]].sum()
                val1 = rate(t1_sum["첫주문30일"], t1_sum["가입자"])
                st.metric("30일 첫 주문 전환율 (INSTA)", f"{val1:.1f}%")
            else:
                st.metric("30일 첫 주문 전환율 (INSTA)", "데이터 없음")

            st.caption("대시보드에서: 탐색 탭 · 비교 기준 가입채널 · 드릴다운 INSTA_첫주문쿠폰")

    # ------------------------------------------------------------
    # 카드 2 · INSTA 재주문
    # ------------------------------------------------------------
    with act_col2:
        with st.container(border=True):
            st.markdown("**카드 2 · INSTA 재주문**")
            st.markdown(
                "- 문제: INSTA 가입자의 30일 재주문율 44.5% (다른 채널 72.6–77.3%)\n"
                "- 근거: 첫 주문 고객 456명 중 203명만 30일 안에 다시 주문\n"
                "- 성격: 처음부터 그런 구조\n"
                "- 액션: 실험: INSTA 첫 주문 고객 일부에게 두 번째 주문 혜택을 주고 30일 재주문율 비교\n"
                "- 우선순위: 효과 불확실 · 실행 쉬움 → 실험부터"
            )

            # 카드 2 KPI 계산 (가입채널 == "INSTA_첫주문쿠폰", 마지막 3개월, rd 사용)
            c2_data = rd_period[
                (rd_period["가입채널"] == "INSTA_첫주문쿠폰") & (rd_period["가입월"].isin(rd_last3_months))
            ]
            if not c2_data.empty:
                t2_sum = c2_data[["첫주문고객", "재주문30일"]].sum()
                val2 = rate(t2_sum["재주문30일"], t2_sum["첫주문고객"])
                st.metric("30일 재주문율 (INSTA)", f"{val2:.1f}%")
            else:
                st.metric("30일 재주문율 (INSTA)", "데이터 없음")

            st.caption("대시보드에서: 개요 탭 ③ 가입 채널별 30일 재주문율")
