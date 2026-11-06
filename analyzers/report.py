"""Shared result format used by every analyzer."""

STRENGTH_POINTS = {"strong": 3, "medium": 2, "weak": 1}


class Report:
    """Collects evidence and turns it into a ranked verdict.

    Each piece of evidence may vote for a candidate (e.g. "Midjourney").
    Confidence comes from the strongest single signal, so many weak style
    hints never add up to a "high" verdict on their own.
    """

    def __init__(self, kind):
        self.kind = kind
        self.scores = {}
        self.best_strength = {}
        self.evidence = []
        self.details = {}
        self.prompt = {}
        self.sections = []
        self.notes = []
        self.raw = {}

    def add(self, candidate, strength, signal, detail=""):
        self.evidence.append({
            "candidate": candidate,
            "strength": strength,
            "signal": signal,
            "detail": str(detail)[:600],
        })
        if candidate:
            points = STRENGTH_POINTS[strength]
            self.scores[candidate] = self.scores.get(candidate, 0) + points
            previous_best = self.best_strength.get(candidate, 0)
            self.best_strength[candidate] = max(previous_best, points)

    def section(self, title, body):
        if body:
            self.sections.append({"title": title, "body": str(body)})

    def to_dict(self, fallback_label="No AI fingerprint found", fallback_confidence="none"):
        ranked = sorted(self.scores.items(), key=lambda item: -item[1])
        if ranked:
            label, score = ranked[0]
            best = self.best_strength[label]
            if best == 3:
                confidence = "high"
            elif best == 2 or score >= 4:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            label = fallback_label
            confidence = fallback_confidence
        return {
            "kind": self.kind,
            "verdict": {"label": label, "confidence": confidence},
            "candidates": [{"name": name, "score": score} for name, score in ranked],
            "prompt": self.prompt,
            "details": self.details,
            "sections": self.sections,
            "evidence": self.evidence,
            "notes": self.notes,
            "raw": self.raw,
        }
