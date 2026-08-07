"""Throwaway: does lexical (TF-IDF) scoring separate what dense embeddings can't?

    python scripts/hybrid_experiment.py michigan
    python scripts/hybrid_experiment.py gaza
    python scripts/hybrid_experiment.py michigan 0.3     # optional alpha

Dense embeddings blur proper nouns -- "Benson wins" and "James wins" both encode
as "a person winning a Michigan primary". TF-IDF weights rare terms heavily, so
the names should dominate instead.

IDF is fitted over the WHOLE corpus, not the matching subset. That is what makes
"Michigan" nearly free and "Benson" expensive.

What you are looking for: same-story pairs stay high in the lexical column,
different-story pairs collapse. If lexical just mirrors dense, it adds nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import Article, Outlet, make_engine, make_session_factory
from worker.embed import strip_html

LIMIT = 25
ALPHA = 0.5


def doc_text(headline: str, lede: str | None) -> str:
    parts = [headline]
    if lede:
        parts.append(lede)
    return strip_html("\n".join(parts))


def main() -> int:
    args = sys.argv[1:]
    alpha = ALPHA
    if args:
        try:
            alpha = float(args[-1])
            args.pop()
        except ValueError:
            pass

    term = " ".join(args).strip()
    if not term:
        print("usage: python scripts/hybrid_experiment.py <term> [alpha]")
        return 1

    Session = make_session_factory(make_engine())
    with Session() as session:
        corpus = (
            session.query(Article.id, Article.headline, Article.lede, Article.embedding)
            .filter(Article.embedding.is_not(None))
            .all()
        )
        subset = (
            session.query(Article, Outlet)
            .join(Outlet, Outlet.id == Article.outlet_id)
            .filter(
                Article.embedding.is_not(None),
                Article.headline.ilike(f"%{term}%"),
            )
            .order_by(Article.published_at.desc().nullslast())
            .limit(LIMIT)
            .all()
        )

    if len(subset) < 3:
        print(f"only {len(subset)} articles match {term!r}")
        return 1

    # IDF over the entire corpus is the whole point -- it is what tells the
    # scorer that "Michigan" is common and "Benson" is not.
    texts = [doc_text(h, lede) for _, h, lede, _ in corpus]
    position = {aid: i for i, (aid, _, _, _) in enumerate(corpus)}
    vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=2)
    tfidf = vectorizer.fit_transform(texts)  # rows are L2-normalised
    print(
        f"IDF fitted over {len(texts)} articles, {len(vectorizer.vocabulary_)} terms\n"
    )

    rows = [(a, o, position[a.id]) for a, o in subset]
    seed, seed_outlet, _ = rows[0]

    dense = np.array([corpus[i][3] for _, _, i in rows], dtype=np.float32)
    dense /= np.linalg.norm(dense, axis=1, keepdims=True)  # halfvec rounding
    dense_sim = dense @ dense[0]

    lex = tfidf[[i for _, _, i in rows]]
    lex_sim = np.asarray((lex @ lex[0].T).todense()).ravel()

    print(f"SEED  [{seed_outlet.name}]  {seed.headline[:78]}\n")
    print(
        f"  {'dense':>6} {'lexical':>8} {'hybrid':>7} {'delta':>7}  outlet / headline"
    )

    scored = []
    for k in range(1, len(rows)):
        a, o, _ = rows[k]
        d, lx = float(dense_sim[k]), float(lex_sim[k])
        scored.append((d, lx, alpha * d + (1 - alpha) * lx, a, o))
    scored.sort(reverse=True, key=lambda r: r[0])  # dense order, as before

    for d, lx, h, a, o in scored:
        print(
            f"  {d:>6.3f} {lx:>8.3f} {h:>7.3f} {h - d:>+7.3f}  "
            f"[{o.name[:16]:<16}] {a.headline[:50]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
