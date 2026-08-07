"""Embed articles so they can be clustered.

Backfill everything:  python -m worker.embed
During ingestion:     ingest.py calls embed_pending() after the fetch loop.

Embeddings are derived data. An article whose embedding is null is simply
picked up on the next run, so a failure here never costs a fetch.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from html.parser import HTMLParser

from common.config import EMBED_BATCH_SIZE, EMBEDDING_MODEL
from common.models import Article, make_engine, make_session_factory

_model = None


def get_model():
    """Loaded once per process -- model load costs a second or two."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(f"loading {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


class _TextExtractor(HTMLParser):
    """Collects text, drops tags. convert_charrefs (on by default) resolves
    &amp; and &#8220; for us, which a regex would leave in the embedding."""

    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self.chunks.append(data)


def strip_html(s: str) -> str:
    parser = _TextExtractor()
    parser.feed(s)
    parser.close()
    return " ".join("".join(parser.chunks).split())


def article_text(article: Article) -> str:
    """The exact string that gets embedded."""
    parts = [strip_html(article.headline)]
    if article.lede:
        parts.append(strip_html(article.lede))
    return "\n".join(parts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch encode.

    normalize_embeddings gives every vector unit length, so cosine similarity
    is a plain dot product and averaging vectors into a centroid behaves
    predictably later.
    """
    vectors = get_model().encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def embed_pending(session, limit: int | None = None) -> int:
    """Embed every article missing an embedding. Returns how many were written."""
    total = 0
    while limit is None or total < limit:
        size = (
            EMBED_BATCH_SIZE if limit is None else min(EMBED_BATCH_SIZE, limit - total)
        )

        batch = (
            session.query(Article)
            .filter(Article.embedding.is_(None))
            .order_by(Article.first_seen_at)
            .limit(size)
            .all()
        )
        if not batch:
            break

        vectors = embed_texts([article_text(a) for a in batch])
        for article, vector in zip(batch, vectors, strict=True):
            article.embedding = vector
        session.commit()

        total += len(batch)
        print(f"  embedded {total}")

    return total


def main() -> int:
    engine = make_engine()
    Session = make_session_factory(engine)
    with Session() as session:
        pending = session.query(Article).filter(Article.embedding.is_(None)).count()
        print(f"{pending} articles need embedding")
        if pending:
            embed_pending(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
