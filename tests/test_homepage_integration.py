import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from scripts.publish_realtime_stats import validate_public_snapshot


class HomepageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.stats_url = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"])
        if element_id == "realtime-statistics":
            self.stats_url = attributes.get("data-stats-url")


class HomepageIntegrationTests(unittest.TestCase):
    def test_homepage_exposes_all_realtime_metric_targets(self):
        parser = HomepageParser()
        parser.feed(Path("index.html").read_text(encoding="utf-8"))

        expected_ids = {
            "realtime-statistics",
            "stats-trajectories",
            "stats-trajectories-arrow",
            "stats-trajectories-rate",
            "stats-tasks",
            "stats-tasks-arrow",
            "stats-tasks-rate",
            "stats-duration",
            "stats-duration-arrow",
            "stats-duration-rate",
            "stats-status",
        }
        self.assertTrue(expected_ids.issubset(parser.ids))
        self.assertEqual(parser.stats_url, "./data/realtime-stats.json")
        self.assertIn(
            "realtime-stats.js?v=20260724-complete-day-tasks",
            parser.scripts,
        )

    def test_toc_includes_realtime_statistics_before_abstract(self):
        homepage = Path("index.html").read_text(encoding="utf-8")
        toc_realtime = homepage.index('href="#realtime-statistics"')
        toc_abstract = homepage.index('href="#abstract"')
        script = Path("script.js").read_text(encoding="utf-8")

        self.assertLess(toc_realtime, toc_abstract)
        self.assertIn("Real-time Statistics", homepage)
        self.assertIn("tocSectionIds", script)
        self.assertIn("IntersectionObserver", script)

    def test_realtime_title_precedes_requested_metric_layout(self):
        homepage = Path("index.html").read_text(encoding="utf-8")

        self.assertLess(
            homepage.index("stats-heading-title"),
            homepage.index('id="stats-trajectories"'),
        )
        self.assertNotIn("stats-card--status", homepage)
        self.assertIn("stats-card stats-card--trajectories", homepage)
        self.assertLess(
            homepage.index("stats-card--trajectories"),
            homepage.index("stats-card--tasks"),
        )
        self.assertLess(
            homepage.index("stats-card--tasks"),
            homepage.index("stats-card--duration"),
        )
        self.assertEqual(homepage.count('class="stats-growth-arrow"'), 3)
        self.assertEqual(homepage.count('data-direction="potential"'), 3)

    def test_paper_link_and_bibtex_use_the_arxiv_release(self):
        homepage = Path("index.html").read_text(encoding="utf-8")

        self.assertIn(
            '<a href="https://arxiv.org/abs/2607.21588">[paper]</a>',
            homepage,
        )
        self.assertNotIn(
            'href="assets/paper/AXIS-V1_Release.pdf">[paper]</a>',
            homepage,
        )
        for entry in (
            "@article{zhao2026axis,",
            "journal = {arXiv preprint arXiv:2607.21588},",
            "year    = {2026},",
            "url     = {https://arxiv.org/abs/2607.21588}",
        ):
            self.assertIn(entry, homepage)
        for obsolete_entry in (
            "@misc{zhao2026axisgrowablecommunitydrivendata,",
            "eprint={2607.21588},",
            "archivePrefix={arXiv},",
            "primaryClass={cs.RO},",
        ):
            self.assertNotIn(obsolete_entry, homepage)

    def test_homepage_uses_requested_defaults_without_baseline_copy(self):
        homepage = Path("index.html").read_text(encoding="utf-8")
        script = Path("realtime-stats.js").read_text(encoding="utf-8")

        for value in ("1,530,275", "1,816", "13,645 h 7 m"):
            self.assertIn(value, homepage)
        for value in ("1530275", "1816", "49122405"):
            self.assertIn(value, script)
        self.assertNotIn("Collecting hourly baseline", homepage)
        self.assertNotIn("Collecting hourly baseline", script)
        self.assertNotIn(">Baseline<", homepage)
        self.assertNotIn('"Baseline"', script)
        self.assertIn(
            "Data is verified every hour. Task growth uses the latest complete UTC day.",
            homepage,
        )
        self.assertIn("formatTasksDailyRate", script)
        self.assertIn('"Est. "', script)
        self.assertNotIn("Last verified", script)

    def test_stats_use_black_nonwrapping_two_row_layout(self):
        stylesheet = Path("style.css").read_text(encoding="utf-8")
        script = Path("realtime-stats.js").read_text(encoding="utf-8")

        self.assertRegex(
            stylesheet,
            r"(?s)\.stats-strip \{[^}]*"
            r"grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);",
        )
        self.assertRegex(
            stylesheet,
            r"(?s)\.stats-card--trajectories \{[^}]*grid-column: 1 / -1;",
        )
        self.assertRegex(
            stylesheet,
            r"(?s)\.stats-value \{[^}]*color: var\(--ink\);"
            r"[^}]*white-space: nowrap;",
        )
        for selector in (r"\.stats-digit-face", r"\.stats-glyph"):
            self.assertRegex(
                stylesheet,
                rf"(?s){selector} \{{[^}}]*color: var\(--ink\);",
            )
        self.assertIn("stats-digit-track is-entering", script)
        self.assertIn("@keyframes stats-digit-enter", stylesheet)

    def test_hourly_workflow_has_backup_slots_and_a_freshness_gate(self):
        workflow = Path(
            ".github/workflows/realtime-stats.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('cron: "17,37,57 * * * *"', workflow)
        self.assertIn("snapshot_age_seconds < 3000", workflow)
        self.assertIn("should_refresh=${should_refresh}", workflow)
        self.assertIn("expected_ref=${current_ref}", workflow)

    def test_checked_in_snapshot_is_safe_public_data(self):
        snapshot_path = Path("data/realtime-stats.json")
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)

        if payload.get("status") == "ok":
            sanitized, _ = validate_public_snapshot(snapshot_path)
            self.assertEqual(json.loads(sanitized), payload)
            return

        self.assertEqual(payload.get("status"), "awaiting_first_sync")
        expected_keys = {
            "schema_version",
            "status",
            "sample_id",
            "sampled_at",
            "previous_sampled_at",
            "sample_interval_seconds",
            "totals",
            "delta_since_previous",
            "growth_per_hour",
            "tasks_daily",
        }
        self.assertEqual(set(payload), expected_keys)
        self.assertIsNone(payload["sample_id"])
        self.assertIsNone(payload["sampled_at"])
        self.assertIsNone(payload["previous_sampled_at"])
        self.assertIsNone(payload["sample_interval_seconds"])
        for field in ("totals", "delta_since_previous", "growth_per_hour"):
            self.assertEqual(
                set(payload[field]),
                {"trajectories", "tasks", "trajectory_duration_seconds"},
            )
            self.assertTrue(all(value is None for value in payload[field].values()))
        self.assertEqual(
            payload["tasks_daily"],
            {
                "utc_date": None,
                "baseline_total": None,
                "display_utc_date": None,
                "increase": None,
                "basis": "unavailable",
            },
        )


if __name__ == "__main__":
    unittest.main()
