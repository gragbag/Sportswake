"""Classify a comment before it publishes.

Two backends behind one interface, selected by MODERATION_PROVIDER. They
agree on the Verdict they return and on nothing else: OpenAI's classifier
gives calibrated per-category scores that meet numeric thresholds, while the
Groq fallback gets the policy in words and returns a decision. They are NOT
equivalent -- measured side by side, the fallback misses dehumanising
language the classifier catches. It is what you run when the primary is
gone, not an alternative to it.

The three outcomes map onto comments.status:

    visible   nothing crossed its threshold
    removed   something did; never shown to readers
    pending   we could not decide (no key, timeout, 429, malformed reply)

`pending` is a retry state, not a review queue. worker/moderate.py picks
those up and resolves them, which is what keeps a failed classification from
becoming a comment that silently never appears.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import (
    GROQ_API_KEY,
    MODERATION_GROQ_MODEL,
    MODERATION_OPENAI_MODEL,
    MODERATION_OPENAI_URL,
    MODERATION_PROVIDER,
    MODERATION_THRESHOLDS,
    MODERATION_TIMEOUT_SECONDS,
    OPENAI_API_KEY,
    SUMMARY_BASE_URL,
)


class Verdict(NamedTuple):
    status: str  # 'visible' | 'removed' | 'pending'
    reason: str | None


def _post(url: str, payload: dict, token: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Not cosmetic: Groq's edge rejects the default
            # "Python-urllib/x.y" agent with a 403, which silently turned
            # the whole fallback provider into a pending-forever machine.
            "User-Agent": "presswake/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=MODERATION_TIMEOUT_SECONDS) as resp:
        return json.load(resp)


def _scores_openai(body: str) -> dict[str, float]:
    """OpenAI returns calibrated per-category scores directly."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    data = _post(
        MODERATION_OPENAI_URL,
        {"model": MODERATION_OPENAI_MODEL, "input": body},
        OPENAI_API_KEY,
    )
    return data["results"][0]["category_scores"]


# The policy in words, because the fallback model cannot do numbers.
#
# Asking an 8B model for per-category probabilities was tried and does not
# work: it returns round guesses (0.5, 1.0) rather than calibrated scores,
# and at the thresholds tuned for OpenAI it deleted ordinary harsh political
# comment. A boolean decision against an explicit policy is what a small
# model can actually do, so the two backends deliberately differ in shape
# and agree only on the Verdict they return.
_GROQ_POLICY = """\
Decide whether a comment on a news site must be removed.

REMOVE only for: threats of violence; dehumanising language about a group of
people; sexual content involving minors; encouraging suicide or self-harm;
instructions for serious crime.

ALLOW everything else, including: robust political disagreement, harsh
criticism of politicians and journalists, accusations of corruption,
profanity, rudeness, and strongly worded opinions. Political anger is not a
violation.

Reply with JSON only: {"remove": boolean, "reason": string}
"""


def _verdict_groq(body: str) -> Verdict:
    """Fallback backend: a policy decision, not a score."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    data = _post(
        f"{SUMMARY_BASE_URL}/chat/completions",
        {
            "model": MODERATION_GROQ_MODEL,
            "temperature": 0,
            "max_tokens": 120,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _GROQ_POLICY},
                {"role": "user", "content": body},
            ],
        },
        GROQ_API_KEY,
    )
    raw = json.loads(data["choices"][0]["message"]["content"])
    if not isinstance(raw.get("remove"), bool):
        # Shape check, same discipline as summarize.py: JSON mode guarantees
        # syntax, not structure. An unusable answer is not an answer, and
        # classify() turns this into 'pending'.
        raise TypeError("no boolean 'remove' in reply")
    if raw["remove"]:
        return Verdict("removed", str(raw.get("reason", "policy"))[:200])
    return Verdict("visible", None)


def _verdict(scores: dict[str, float]) -> Verdict:
    """Apply per-category thresholds. Strictest category wins."""
    for category, threshold in MODERATION_THRESHOLDS.items():
        value = scores.get(category, 0.0)
        if value >= threshold:
            return Verdict("removed", f"{category} {value:.2f}")
    return Verdict("visible", None)


def classify(body: str) -> Verdict:
    """Never raises. Any failure is 'pending', never 'visible'.

    Failing closed matters most exactly when it is tempting to fail open:
    an exhausted quota or a downed provider is when someone is most likely
    to be probing, and publishing unchecked is the one outcome that cannot
    be undone quietly.
    """
    provider = MODERATION_PROVIDER.lower()
    if provider == "openai" and not OPENAI_API_KEY:
        return Verdict("pending", "no OPENAI_API_KEY")
    if provider == "groq" and not GROQ_API_KEY:
        return Verdict("pending", "no GROQ_API_KEY")

    try:
        if provider == "groq":
            return _verdict_groq(body)
        return _verdict(_scores_openai(body))
    except urllib.error.HTTPError as exc:
        return Verdict("pending", f"http {exc.code}")
    except (urllib.error.URLError, TimeoutError):
        return Verdict("pending", "unreachable")
    except (KeyError, ValueError, TypeError, RuntimeError) as exc:
        # Malformed reply. Same treatment as a failure: we did not get an
        # answer, so we have not decided.
        return Verdict("pending", f"bad response: {type(exc).__name__}")
