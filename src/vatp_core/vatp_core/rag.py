"""RAG memory: BM25 retrieval over the robot's safety constraints and recovery procedures.

BM25 (pure Python) was chosen over dense embeddings deliberately: zero model download,
deterministic ranking (reproducible benchmarks), sub-millisecond latency, and the corpus
is small and keyword-rich. A dense retriever can be swapped in behind ``Retriever``.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
_TOKEN = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class Chunk:
    id: str  # e.g. SC-01
    title: str
    tags: str
    text: str
    source: str

    def render(self) -> str:
        return f"[{self.id}] {self.title}: {self.text}"


def _tokens(s: str) -> list[str]:
    out: list[str] = []
    for t in _TOKEN.findall(s.lower()):
        out.append(t)
        if "_" in t:  # NAV_BLOCKED also matches nav / blocked
            out.extend(p for p in t.split("_") if p)
    return out


def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in sorted(directory.glob("*.md")):
        for block in re.split(r"^## ", f.read_text(), flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            cid, _, title = head.partition(" ")
            lines = body.strip().splitlines()
            tags = ""
            if lines and lines[0].startswith("tags:"):
                tags = lines.pop(0)[5:].strip()
            chunks.append(Chunk(cid, title.strip(), tags, " ".join(l.strip() for l in lines), f.name))
    return chunks


class Retriever:
    def __init__(self, chunks: list[Chunk] | None = None, k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks if chunks is not None else load_chunks()
        self.k1, self.b = k1, b
        # tags are weighted by repetition: they are curated keywords
        self._docs = [Counter(_tokens(f"{c.title} {c.tags} {c.tags} {c.text}")) for c in self.chunks]
        self._len = [sum(d.values()) for d in self._docs]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 1.0
        df: Counter[str] = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, k: int = 4, prefix: str | None = None) -> list[Chunk]:
        q = _tokens(query)
        scored: list[tuple[float, int]] = []
        for i, (c, d) in enumerate(zip(self.chunks, self._docs)):
            if prefix and not c.id.startswith(prefix):
                continue
            s = 0.0
            for t in q:
                f = d.get(t, 0)
                if f:
                    s += self._idf.get(t, 0.0) * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self._len[i] / self._avg))
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.chunks[i] for _, i in scored[:k]]

    def always(self, prefix: str) -> list[Chunk]:
        """All chunks of a family (e.g. every SC-* safety rule is always shown)."""
        return [c for c in self.chunks if c.id.startswith(prefix)]
