import os
import sys
from pathlib import Path
from typing import List

# プロジェクトルートを sys.path に追加（直接実行・モジュール実行の両対応）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.docstore.document import Document

try:
    from langchain_community.embeddings import HuggingFaceEmbeddings
except ImportError:
    from langchain.embeddings import HuggingFaceEmbeddings

try:
    from langchain_community.vectorstores import Chroma
except ImportError:
    from langchain.vectorstores import Chroma

from app.loader import load_and_chunk_manuals


def create_vector_index(
    data_dir: str = "data",
    persist_directory: str = "chroma_db",
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> Chroma:
    """
    Wordマニュアルから抽出したチャンクをローカルEmbeddingモデルでベクトル化し、
    ChromaDBに永続化保存する。
    """
    # 相対パスの場合はプロジェクトルート基準で解決
    data_path = Path(data_dir)
    if not data_path.is_absolute():
        data_path = PROJECT_ROOT / data_dir

    persist_path = Path(persist_directory)
    if not persist_path.is_absolute():
        persist_path = PROJECT_ROOT / persist_directory

    print(f"[1/4] マニュアルの読み込みとチャンキングを開始します (対象ディレクトリ: {data_path})...")
    raw_chunks = load_and_chunk_manuals(data_dir=str(data_path))
    print(f"      -> {len(raw_chunks)} 件のチャンクを抽出しました。")

    print("[2/4] LangChain Document オブジェクトへの変換中...")
    documents = [
        Document(
            page_content=chunk["content"],
            metadata=chunk["metadata"],
        )
        for chunk in raw_chunks
    ]

    print(f"[3/4] Embeddingモデルを読み込み中: {model_name}...")
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    print(f"[4/4] ChromaDBへベクトルデータを保存中 (保存先ディレクトリ: {persist_path})...")
    vector_db = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(persist_path),
    )

    if hasattr(vector_db, "persist"):
        try:
            vector_db.persist()
        except Exception:
            pass

    print(f"✓ インデックス作成が完了しました。保存先: {persist_path}")
    return vector_db


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    create_vector_index()
