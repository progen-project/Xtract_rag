"""
guard.py
────────
Importable LLM Guard gate — V2 (semi-supervised classifier).

Usage:
    from guard import Guard

    guard = Guard()
    guard.check("What is a choke line?")     # → True
    guard.check("How do I make pasta?")      # → False

    guard.check_many(["...", "..."])         # → [True, False]
    guard.details("What is a choke line?")   # → full dict with probability

    # Module-level one-liner:
    from guard import is_relevant
    if is_relevant("What is a choke line?"):
        ...
"""

import json
import os
import pickle
import re
import warnings
warnings.filterwarnings("ignore")

import numpy as np


_DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_model")


class Guard:
    """
    LLM relevance gate backed by a Logistic Regression classifier
    trained on domain docs (positive) + Q&A negatives.

    Parameters
    ----------
    model_dir : path to guard_model/ folder
    threshold : override decision threshold (0.0–1.0). None = use saved value.
    """

    def __init__(
        self,
        model_dir: str        = _DEFAULT_MODEL_DIR,
        threshold: float | None = None,
    ):
        self._load(model_dir, threshold)

    # ────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────

    def check(self, question: str, verbose: bool = False) -> bool:
        """
        Returns True if the question is relevant to the domain.
        """
        result = self.details(question)
        if verbose:
            self._print(result)
        return result["relevant"]

    def check_many(self, questions: list[str], verbose: bool = False) -> list[bool]:
        """Batch version. Returns list of bool in same order as input."""
        results = self._predict_batch(questions)
        if verbose:
            for r in results:
                self._print(r)
        return [r["relevant"] for r in results]

    def details(self, question: str) -> dict:
        """
        Full scoring dict for one question:
            {
              "question"    : str,
              "relevant"    : bool,
              "label"       : "RELEVANT" | "IRRELEVANT",
              "probability" : float   ← P(relevant), 0.0 – 1.0
            }
        """
        return self._predict_batch([question])[0]

    # ────────────────────────────────────────────────────────────
    # Internal
    # ────────────────────────────────────────────────────────────

    def _load(self, model_dir: str, threshold_override) -> None:
        if not os.path.isdir(model_dir):
            raise FileNotFoundError(
                f"Guard model directory not found: '{model_dir}'\n"
                "Train the model first:  python guard_pipeline.py --mode train ..."
            )

        with open(os.path.join(model_dir, "meta.json"), "r") as f:
            self._meta = json.load(f)

        clf_path = os.path.join(model_dir, "classifier.pkl")
        if not os.path.exists(clf_path):
            raise FileNotFoundError(
                f"classifier.pkl not found in '{model_dir}'.\n"
                "This model directory was created with the old V1 pipeline.\n"
                "Please retrain with the updated guard_pipeline.py."
            )
        with open(clf_path, "rb") as f:
            self._clf = pickle.load(f)

        self._threshold = (
            threshold_override
            if threshold_override is not None
            else self._meta["threshold"]
        )

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("Run:  pip install sentence-transformers")

        self._encoder = SentenceTransformer(self._meta["encoder_name"])

    def _clean(self, text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.lower()
        text = re.sub(r"\$[^$]*\$",         " ", text)
        text = re.sub(r"\[image[^\]]*\]",   " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\[table[^\]]*\]",   " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>",           " ", text)
        text = re.sub(r"https?://\S+",      " ", text)
        text = re.sub(r"^\s*[\*\-\·\•]\s*", " ", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _predict_batch(self, questions: list[str]) -> list[dict]:
        cleaned = [self._clean(q) for q in questions]
        X = self._encoder.encode(
            cleaned,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

        probs    = self._clf.predict_proba(X)[:, 1]
        relevant = probs >= self._threshold

        return [
            {
                "question":    q,
                "relevant":    bool(r),
                "label":       "RELEVANT" if r else "IRRELEVANT",
                "probability": round(float(p), 4),
            }
            for q, r, p in zip(questions, relevant, probs)
        ]

    @staticmethod
    def _print(r: dict) -> None:
        flag = "✓" if r["relevant"] else "✗"
        print(
            f"  {flag} [{r['label']:>10}]  "
            f"P(relevant)={r['probability']:.4f}  "
            f"|  {r['question']}"
        )

    def __repr__(self) -> str:
        return (
            f"Guard("
            f"encoder='{self._meta['encoder_name']}', "
            f"trained_on={self._meta['n_positive']:,}pos+{self._meta['n_negative']:,}neg, "
            f"threshold={self._threshold:.2f})"
        )


# ════════════════════════════════════════════════════════════════
# Module-level convenience
# ════════════════════════════════════════════════════════════════

_default_guard: Guard | None = None


def is_relevant(question: str, model_dir: str = _DEFAULT_MODEL_DIR) -> bool:
    """
    One-liner gate. Loads model on first call, reuses for all subsequent calls.

        from guard import is_relevant
        if is_relevant("What is a choke line?"):
            # pass to LLM
    """
    global _default_guard
    if _default_guard is None:
        _default_guard = Guard(model_dir)
    return _default_guard.check(question)


# ════════════════════════════════════════════════════════════════
# CLI — quick test
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("\n" + "═"*60)
    print("  GUARD V2 — gate test")
    print("═"*60)

    guard = Guard()
    print(f"\n  {guard}\n")

    questions = sys.argv[1:] if len(sys.argv) > 1 else [
        "What is a choke line?",
        "How do you control a kick in a wellbore?",
        "What is the capital of France?",
        "How do I make pasta?",
        "What's the color of the watch?",
        "Explain the driller method for well control.",
        "What did the admissions policy of the University of Texas violate?",
        "What equipment is used in blowout prevention?",
    ]

    print("  Single check (verbose):")
    for q in questions:
        guard.check(q, verbose=True)

    print("\n  Batch → list of bool:")
    bools = guard.check_many(questions)
    for q, b in zip(questions, bools):
        tag = "TRUE " if b else "FALSE"
        print(f"    {tag}  ←  {q}")

    print("\n  Details for first question:")
    d = guard.details(questions[0])
    for k, v in d.items():
        print(f"    {k:<12} : {v}")