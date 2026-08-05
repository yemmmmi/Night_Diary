"""Chinese diary text chunking for RAG indexing."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.domain.rag.types import Chunk

_CN_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "：",
    "，",
    ".",
    "!",
    "?",
    ":",
    ",",
    " ",
    "",
]

_PARENT_CHILD_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", ".", "!", "?", " ", ""]


class ChunkSplitter:
    """Split diary text into retrieval-sized chunks.

    Standard mode uses LangChain ``RecursiveCharacterTextSplitter`` (V1
    ``ChunkSplitter``). Optional parent-child mode merges V1
    ``ParentChildChunker``: small child chunks for retrieval plus a parent
    chunk holding the full diary for context expansion in B-3.
    """

    def __init__(
        self,
        *,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 128,
        parent_child: bool = False,
        child_chunk_size: int = 250,
        child_overlap: int = 30,
        min_child_content: int = 50,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.parent_child = parent_child
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap
        self.min_child_content = min_child_content

        self._splitter = RecursiveCharacterTextSplitter(
            separators=_CN_SEPARATORS,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            keep_separator=True,
        )
        self._child_splitter = RecursiveCharacterTextSplitter(
            separators=_PARENT_CHILD_SEPARATORS,
            chunk_size=self.child_chunk_size,
            chunk_overlap=self.child_overlap,
            length_function=len,
            keep_separator=True,
        )

    def split(self, content: str) -> list[str]:
        """Return chunk texts; short content stays a single segment."""
        if len(content) < self.min_chunk_size:
            return [content]
        return self._splitter.split_text(content)

    def split_chunks(
        self,
        content: str,
        *,
        diary_id: str,
        date: str = "",
        tags: str = "",
    ) -> list[Chunk]:
        """Split content and attach diary metadata."""
        if self.parent_child:
            parent, children = self.split_parent_child(
                content,
                diary_id=diary_id,
                date=date,
                tags=tags,
            )
            return [parent, *children]

        texts = self.split(content)
        total = len(texts)
        return [
            Chunk(
                content=text,
                diary_id=diary_id,
                chunk_index=index,
                chunk_total=total,
                date=date,
                tags=tags,
                doc_id=f"diary_{diary_id}_chunk_{index}",
                doc_type="chunk",
            )
            for index, text in enumerate(texts)
        ]

    def split_parent_child(
        self,
        content: str,
        *,
        diary_id: str,
        date: str = "",
        tags: str = "",
    ) -> tuple[Chunk, list[Chunk]]:
        """Return one parent chunk (full diary) and child chunks for retrieval."""
        parent_id = f"parent_{diary_id}"
        parent = Chunk(
            content=content,
            diary_id=diary_id,
            chunk_index=0,
            chunk_total=1,
            date=date,
            tags=tags,
            doc_id=parent_id,
            doc_type="parent",
        )

        if len(content) < self.min_child_content:
            child = Chunk(
                content=content,
                diary_id=diary_id,
                chunk_index=0,
                chunk_total=1,
                date=date,
                tags=tags,
                doc_id=f"child_{diary_id}_0",
                doc_type="child",
                parent_id=parent_id,
            )
            return parent, [child]

        texts = self._child_splitter.split_text(content)
        total = len(texts)
        children = [
            Chunk(
                content=text,
                diary_id=diary_id,
                chunk_index=index,
                chunk_total=total,
                date=date,
                tags=tags,
                doc_id=f"child_{diary_id}_{index}",
                doc_type="child",
                parent_id=parent_id,
            )
            for index, text in enumerate(texts)
        ]
        return parent, children

    @staticmethod
    def extract_parent_id(child_doc_id: str) -> str | None:
        """Parse ``parent_{diary_id}`` from a child document id."""
        if not child_doc_id.startswith("child_"):
            return None
        remainder = child_doc_id.removeprefix("child_")
        if "_" not in remainder:
            return None
        diary_part, _index_part = remainder.rsplit("_", 1)
        if not diary_part:
            return None
        return f"parent_{diary_part}"
