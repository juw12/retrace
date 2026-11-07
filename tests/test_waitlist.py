import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import waitlist_tally as wt  # noqa: E402

FORM_BODY = """### How many client websites do you look after?

6-25

### Country

Germany

### Would you take the founding offer (EUR 15/month for life, 30-day refund)?

{answer}

### What would you want in the client report?

_No response_
"""


def issue(number, answer="Yes", author="agency-dev", labels=("waitlist",), title="Retrace Agency waitlist", body=None):
    return {"number": number, "title": title, "user": {"login": author}, "state": "open",
            "labels": [{"name": name} for name in labels],
            "body": FORM_BODY.format(answer=answer) if body is None else body}


class WaitlistTests(unittest.TestCase):
    def test_form_answers(self):
        for answer in ("Yes", "Maybe", "No"):
            self.assertEqual(wt.parse_answer(FORM_BODY.format(answer=answer)), answer.lower())
        self.assertIsNone(wt.parse_answer(FORM_BODY.format(answer="_No response_")))

    def test_old_free_text_issue(self):
        unedited = "- Would you take the founding offer (EUR 15/month for life, 30-day refund)? yes / maybe / no"
        self.assertIsNone(wt.parse_answer(unedited))
        self.assertEqual(wt.parse_answer(unedited.replace("yes / maybe / no", "yes")), "yes")

    def test_tally_skips_owner_tracker_and_other_issues(self):
        issues = [
            issue(1, "Yes"),
            issue(2, "Maybe"),
            issue(3, "Yes", author="juw12"),
            issue(4, labels=("waitlist-tally",), title="Retrace Agency waitlist: live tally", body="tally"),
            issue(5, labels=("bug",), title="Crash on image", body="it crashed"),
            issue(6, "No", labels=()),
        ]
        result = wt.tally(issues, owner="juw12")
        self.assertEqual(result["counts"], {"yes": 1, "maybe": 1, "no": 1, "unanswered": 0})
        self.assertEqual([entry["number"] for entry in result["entries"]], [1, 2, 3, 6])
        self.assertFalse(next(entry for entry in result["entries"] if entry["number"] == 3)["counted"])

    def test_decision_follows_the_success_line(self):
        self.assertIn("Running", wt.decision(4, date(2026, 11, 20)))
        self.assertIn("met", wt.decision(10, date(2026, 11, 20)))
        self.assertIn("Rework", wt.decision(5, date(2026, 11, 29)))
        self.assertIn("Stop", wt.decision(2, date(2026, 11, 29)))

    def test_render_mentions_counts_and_deadline(self):
        text = wt.render(wt.tally([issue(7)], owner="juw12"), date(2026, 11, 10))
        self.assertIn("| Yes | 1 |", text)
        self.assertIn("2026-11-28", text)
        self.assertIn("#7 (yes)", text)


if __name__ == "__main__":
    unittest.main()
