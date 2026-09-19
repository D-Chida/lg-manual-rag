import os
import requests
import streamlit as st

# 1. ページ設定
st.set_page_config(
    page_title="自治体窓口マニュアル検索AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

# カード内リストおよび見出しの視認性を高めるCSSスタイル調整
st.markdown(
    """
    <style>
    /* アラートカード内の見出し・リスト項目の行間と視認性調整 */
    .stAlert li {
        margin-bottom: 0.45rem;
        line-height: 1.6;
    }
    .stAlert strong {
        display: inline-block;
        margin-top: 0.2rem;
        margin-bottom: 0.35rem;
        font-size: 1.02rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# API接続先（デフォルト: http://localhost:8000）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def format_to_markdown(text: str) -> str:
    """
    テキスト内の見出し（【...】）や箇条書き（・ / 1. 2. 等）を
    Markdownとして確実に改行・整然としたリストとして表示されるよう整形する。
    """
    if not text:
        return ""

    lines = text.strip().split("\n")
    formatted_parts: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 見出し項目（例: 【市民への案内要点】, 【端末操作フロー】）
        if stripped.startswith("【") and "】" in stripped:
            if formatted_parts:
                formatted_parts.append("")  # 前に空行を挿入
            formatted_parts.append(f"**{stripped}**")
            formatted_parts.append("")  # 見出し直後に空行を入れてリストと明確に分離
        # 箇条書き（・）で始まる行 -> Markdownのリスト項目 (- ) に変換
        elif stripped.startswith("・"):
            formatted_parts.append(f"- {stripped[1:].strip()}")
        # 番号付きリスト（1. 2. 等）
        elif len(stripped) >= 2 and stripped[0].isdigit() and stripped[1] in [".", "、"]:
            formatted_parts.append(f"{stripped[0]}. {stripped[2:].strip()}")
        elif len(stripped) >= 3 and stripped[:2].isdigit() and stripped[2] in [".", "、"]:
            formatted_parts.append(f"{stripped[:2]}. {stripped[3:].strip()}")
        else:
            # 通常テキスト行は末尾2スペースを付与してMarkdown改行を保証
            formatted_parts.append(f"{stripped}  ")

    return "\n".join(formatted_parts)


# -------------------------------------------------------------------
# 状態管理（Session State）の初期化
# -------------------------------------------------------------------
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "user_query_input" not in st.session_state:
    st.session_state.user_query_input = ""
if "execute_search" not in st.session_state:
    st.session_state.execute_search = False
if "search_result" not in st.session_state:
    st.session_state.search_result = None


def on_quick_search_click(selected_text: str):
    """サイドバーのクイック検索ボタン押下時のコールバック"""
    st.session_state.search_query = selected_text
    st.session_state.user_query_input = selected_text
    st.session_state.execute_search = True


# タイトル・概要
st.title("🏛️ 自治体窓口マニュアル検索AI")
st.caption("上下水道局・窓口職員向け：市民からの問い合わせに対する迅速な判断・説明および基幹システム操作フローの照合")

# -------------------------------------------------------------------
# サイドバー: クイック検索（窓口頻出事案）
# -------------------------------------------------------------------
with st.sidebar:
    st.header("📌 クイック検索（窓口頻出事案）")
    st.caption("ボタンをクリックすると即座にマニュアル照合を実行します。")

    quick_items = [
        ("💧", "漏水で水道料金が高くなった"),
        ("📝", "引っ越しに伴う名義変更の手続き"),
        ("⚠️", "検針値が急増してアラートが出た"),
        ("❌", "水道料金が未払い・滞納の相談"),
    ]

    for icon, q_text in quick_items:
        st.button(
            f"{icon} {q_text}",
            use_container_width=True,
            on_click=on_quick_search_click,
            args=(q_text,),
            key=f"quick_btn_{q_text}",
        )

    st.markdown("---")
    st.markdown("**接続先API:**")
    st.code(f"{API_BASE_URL}/ask", language="text")

# -------------------------------------------------------------------
# メイン画面: 入力フォーム
# -------------------------------------------------------------------
query_input = st.text_input(
    label="市民からの問い合わせ内容・質問を入力してください",
    value=st.session_state.user_query_input,
    placeholder="例: 漏水で水道料金が高くなった / 引っ越しで水道を使いたい",
    key="user_query_input",
)

col_btn, _ = st.columns([1, 4])
with col_btn:
    manual_search_clicked = st.button(
        "🔍 マニュアルを照合する", type="primary", use_container_width=True
    )

if manual_search_clicked:
    st.session_state.search_query = query_input
    st.session_state.execute_search = True

# -------------------------------------------------------------------
# 共通API呼び出し処理
# -------------------------------------------------------------------
if st.session_state.execute_search:
    target_query = st.session_state.search_query.strip()
    st.session_state.execute_search = False  # フラグリセット

    if not target_query:
        st.warning("⚠️ 質問文を入力してください。")
    else:
        with st.spinner("関係規定およびシステム操作手順を照合中..."):
            try:
                response = requests.get(
                    f"{API_BASE_URL}/ask",
                    params={"q": target_query},
                    timeout=10,
                )
                if response.status_code == 200:
                    st.session_state.search_result = response.json()
                else:
                    st.error(
                        f"APIエラーが発生しました (HTTP {response.status_code}): {response.text}"
                    )
                    st.session_state.search_result = None
            except requests.exceptions.RequestException as e:
                st.error(
                    f"FastAPIバックエンドへの接続に失敗しました: {e}\n\nFastAPIサーバー ({API_BASE_URL}) が起動しているかご確認ください。"
                )
                st.session_state.search_result = None

# -------------------------------------------------------------------
# 4分割の視認性レイアウト表示
# -------------------------------------------------------------------
if st.session_state.get("search_result"):
    data = st.session_state.search_result
    st.markdown("---")

    # ① 結論: 最上部に強調表示
    st.subheader("💡 判断の結論")
    conclusion_text = format_to_markdown(data.get("conclusion", "結論情報がありません"))
    st.success(conclusion_text)

    # ② 市民向け説明 & 職員アクション: 左右2列に分割
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("### 🗣️ 市民への説明材料（適用基準・算定式）")
        explanation_text = format_to_markdown(
            data.get("explanation_for_citizen", "市民向け説明がありません")
        )
        st.info(explanation_text)

    with col_right:
        st.markdown("### 💻 職員の端末操作手順（画面ID・コード）")
        staff_text = format_to_markdown(
            data.get("staff_action", "操作手順情報がありません")
        )
        st.warning(staff_text)

    # ③ トレーサビリティ: 参照元マニュアルの折りたたみ表示
    with st.expander("📚 参照マニュアルおよび根拠規定（トレーサビリティ）", expanded=False):
        refs = data.get("references", [])
        if refs:
            for idx, ref in enumerate(refs, 1):
                st.markdown(f"**[{idx}] 参照元マニュアル**: `{ref.get('source', '')}`")
                st.markdown(f"- **該当章・見出し**: {ref.get('section', '')}")
        else:
            st.write("参照マニュアル情報はありません（未収録業務またはフォールバック対応）。")
