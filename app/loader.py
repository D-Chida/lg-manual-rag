import os
from pathlib import Path
from typing import Any, Dict, List
from docx import Document


def load_and_chunk_manuals(data_dir: str = "data") -> List[Dict[str, Any]]:
    """
    指定されたディレクトリ内のWordファイル(.docx)を走査し、
    見出し（Heading/Title）単位でセクションを分割・チャンキングして返却する。
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"指定されたディレクトリが存在しません: {data_dir}")

    # 一時ファイル (~$ で始まるファイル) を除外して .docx ファイルを取得
    docx_files = sorted(
        [f for f in data_path.glob("*.docx") if not f.name.startswith("~$")]
    )

    chunks: List[Dict[str, Any]] = []

    for file_path in docx_files:
        doc = Document(file_path)
        current_section: str | None = None
        current_paragraphs: List[str] = []

        def flush_current_chunk():
            if current_section is not None and current_paragraphs:
                content = "\n".join(current_paragraphs).strip()
                if content:
                    chunks.append(
                        {
                            "content": content,
                            "metadata": {
                                "source": file_path.name,
                                "section": current_section,
                            },
                        }
                    )

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            style_name = p.style.name if p.style else ""
            is_heading = "heading" in style_name.lower() or "title" in style_name.lower()

            if is_heading:
                # 既存セクションを確定してチャンク化
                flush_current_chunk()
                current_section = text
                current_paragraphs = [text]
            else:
                if current_section is None:
                    # 先頭に見出しがない場合のフォールバック
                    current_section = "概要"
                    current_paragraphs = []
                current_paragraphs.append(text)

        # ファイル末尾のセクションを確定
        flush_current_chunk()

    return chunks


if __name__ == "__main__":
    import sys

    # Windowsコンソールでの文字化け防止
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    chunks = load_and_chunk_manuals("data")
    print(f"抽出チャンク総数: {len(chunks)} 件\n")

    if chunks:
        first = chunks[0]
        print("【先頭チャンクのメタデータ】")
        print(f"  source : {first['metadata']['source']}")
        print(f"  section: {first['metadata']['section']}")
        print("\n【先頭チャンクの本文冒頭（最大200文字）】")
        preview = first["content"][:200] + ("..." if len(first["content"]) > 200 else "")
        print(preview)
        print("-" * 50)

        # 抽出された全セクションの一覧を表示
        print("【抽出セクション一覧】")
        for i, c in enumerate(chunks, start=1):
            source = c["metadata"]["source"]
            section = c["metadata"]["section"]
            length = len(c["content"])
            print(f"[{i:02d}] {source} | {section} ({length} 文字)")
