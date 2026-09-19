from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# プロジェクトルートを sys.path に追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from langchain_community.embeddings import HuggingFaceEmbeddings
except ImportError:
    from langchain.embeddings import HuggingFaceEmbeddings

try:
    from langchain_community.vectorstores import Chroma
except ImportError:
    from langchain.vectorstores import Chroma

from app.generator import BaseGenerator, get_generator

PERSIST_DIR = PROJECT_ROOT / "chroma_db"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 常駐化用グローバル変数
vector_store: Chroma | None = None
generator: BaseGenerator | None = None


def get_vector_store() -> Chroma:
    """ChromaDB ベクターストアを取得（未初期化の場合は初期化）"""
    global vector_store
    if vector_store is None:
        if not PERSIST_DIR.exists():
            raise RuntimeError(f"ChromaDB ディレクトリが存在しません: {PERSIST_DIR}")
        embeddings = HuggingFaceEmbeddings(
            model_name=MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        vector_store = Chroma(
            persist_directory=str(PERSIST_DIR),
            embedding_function=embeddings,
        )
    return vector_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーション起動時および終了時のライフサイクル管理"""
    global generator
    print("FastAPI起動処理: 回答生成エンジンおよびChromaDBを読み込み中...")
    generator = get_generator()
    get_vector_store()
    print("FastAPI起動処理完了: ベクターストア常駐化完了。")
    yield
    print("FastAPI終了処理完了。")


app = FastAPI(
    title="自治体DX 業務マニュアル検索API",
    lifespan=lifespan,
)


# レスポンスモデル定義
class ReferenceItem(BaseModel):
    source: str = Field(..., description="参照元マニュアルファイル名")
    section: str = Field(..., description="参照章・見出し")


class AskResponse(BaseModel):
    conclusion: str = Field(..., description="質問に対する直接的な結論（減免対象の可否など）")
    explanation_for_citizen: str = Field(..., description="市民への納得感ある説明材料（適用基準や算定式）")
    staff_action: str = Field(..., description="職員が端末等で取るべき操作フロー（画面IDやコード）")
    references: List[ReferenceItem] = Field(..., description="参照したマニュアル名と章名のリスト")


@app.get("/", summary="ヘルスチェック")
def health_check():
    return {"status": "healthy", "service": "lg-manual-rag"}


@app.get("/ask", response_model=AskResponse, summary="窓口職員向け業務マニュアル検索・構造化回答")
def ask(
    q: str = Query(..., description="窓口職員からの質問文（例: トイレの故障による水漏れは減免できるか？）")
):
    try:
        vs = get_vector_store()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"ベクターストアの読み込みに失敗しました: {e}"
        )

    # 類似度検索で上位2件 (k=2) を取得
    docs = vs.similarity_search(q, k=2)

    retrieved_docs = [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
        }
        for doc in docs
    ]

    gen = generator or get_generator()
    answer = gen.generate_answer(query=q, retrieved_docs=retrieved_docs)
    return answer
