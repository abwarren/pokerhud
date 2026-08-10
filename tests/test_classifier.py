"""Unit tests: classifier (bands, R1000 cohort), normalizer, quality."""

import pytest

from mtt import classifier, normalize, quality


class TestClassifyBuyin:
    def test_edges(self):
        assert classifier.classify_buyin(0) == "MICRO"
        assert classifier.classify_buyin(49) == "MICRO"
        assert classifier.classify_buyin(99) == "MICRO"
        assert classifier.classify_buyin(100) == "SMALL"
        assert classifier.classify_buyin(250) == "SMALL"
        assert classifier.classify_buyin(499) == "SMALL"
        assert classifier.classify_buyin(500) == "MID"
        assert classifier.classify_buyin(999) == "MID"

    def test_1000_is_high_band(self):
        # R1000 refers to the R1,000 GUARANTEE tier, not the buy-in
        assert classifier.classify_buyin(1000) == "HIGH"
        assert classifier.classify_buyin(999) == "MID"
        assert classifier.classify_buyin(1001) == "HIGH"

    def test_high(self):
        assert classifier.classify_buyin(2000) == "HIGH"
        assert classifier.classify_buyin(10000) == "HIGH"

    def test_none(self):
        assert classifier.classify_buyin(None) is None


class TestClassifyField:
    def test_edges(self):
        assert classifier.classify_field(1) == "TINY_FIELD"
        assert classifier.classify_field(50) == "TINY_FIELD"
        assert classifier.classify_field(51) == "SMALL_FIELD"
        assert classifier.classify_field(150) == "SMALL_FIELD"
        assert classifier.classify_field(151) == "MEDIUM_FIELD"
        assert classifier.classify_field(500) == "MEDIUM_FIELD"
        assert classifier.classify_field(501) == "LARGE_FIELD"
        assert classifier.classify_field(999) == "LARGE_FIELD"
        assert classifier.classify_field(1000) == "1000_PLUS_FIELD"
        assert classifier.classify_field(5000) == "1000_PLUS_FIELD"

    def test_none_and_zero(self):
        assert classifier.classify_field(None) is None
        assert classifier.classify_field(0) is None


class TestCohort:
    def test_r1000_isolated(self):
        assert classifier.cohort_for("R1000") == "R1000"

    def test_others_carry_band(self):
        assert classifier.cohort_for("MICRO") == "MICRO"
        assert classifier.cohort_for("SMALL") == "SMALL"
        assert classifier.cohort_for("HIGH") == "HIGH"

    def test_none(self):
        assert classifier.cohort_for(None) is None


class TestClassifyTournament:
    def test_r1000_guarantee_tier(self):
        # R1,000 GUARANTEE -> dedicated R1000 cohort regardless of buy-in
        t = classifier.classify_tournament({"buyin": 50, "guarantee": 1000,
                                            "entries": 87})
        assert t["buyin_band"] == "MICRO"
        assert t["cohort"] == "R1000"
        assert t["field_band"] == "SMALL_FIELD"

    def test_buyin_1000_without_r1000_guarantee_is_high(self):
        # a R1,000 buy-in with a normal guarantee is HIGH, not R1000
        t = classifier.classify_tournament({"buyin": 1000, "guarantee": 30000})
        assert t["buyin_band"] == "HIGH"
        assert t["cohort"] == "HIGH"

    def test_non_r1000_guarantee_carries_buyin_band(self):
        t = classifier.classify_tournament({"buyin": 500, "guarantee": 125000})
        assert t["cohort"] == "MID"

    def test_total_entry_cost_fallback(self):
        t = classifier.classify_tournament({"total_entry_cost": 1100})
        assert t["buyin_band"] == "HIGH"
        assert t["buyin_inferred"] is True

    def test_no_buyin(self):
        t = classifier.classify_tournament({"name": "x"})
        assert t["buyin_band"] is None
        assert t["cohort"] is None
        assert t["buyin_inferred"] is False


class TestNormalize:
    def test_money_cleaning(self):
        assert normalize.clean_money("R1,250") == 1250
        assert normalize.clean_money("R 1 250") == 1250
        assert normalize.clean_money("1250.00") == 1250
        assert normalize.clean_money(1250) == 1250
        assert normalize.clean_money(None) is None
        assert normalize.clean_money("") is None
        assert normalize.clean_money("R1M") == 1_000_000
        assert normalize.clean_money("10k") == 10_000
        assert normalize.clean_money("n/a") is None

    def test_int_cleaning(self):
        assert normalize.clean_int("412") == 412
        assert normalize.clean_int("1,100") == 1100
        assert normalize.clean_int(None) is None
        assert normalize.clean_int("abc") is None

    def test_status_mapping(self):
        assert normalize.normalize_status("Late Registration") == "late_reg"
        assert normalize.normalize_status("In Progress") == "running"
        assert normalize.normalize_status("Finished") == "completed"
        assert normalize.normalize_status(None) is None
        assert normalize.normalize_status("Weird") == "weird"

    def test_game_type(self):
        assert normalize.normalize_game_type("NL Hold'em") == "NLHE"
        assert normalize.normalize_game_type("PLO") == "PLO"
        assert normalize.normalize_game_type(None) is None

    def test_datetime_iso_and_epoch(self):
        out = normalize.parse_datetime("2026-08-10T18:00:00+02:00")
        assert out is not None and out.endswith("+00:00")
        assert normalize.parse_datetime(1754323200000) is not None
        assert normalize.parse_datetime(None) is None
        assert normalize.parse_datetime("garbage") is None

    def test_tournament_normalization(self):
        raw = {"site": "pokerbet", "site_tournament_id": "t-1",
               "name": "10k Turbo", "buyin": "R1,000", "fee": "R100",
               "status": "Late Registration", "entries": "87"}
        t = normalize.normalize_tournament(raw)
        assert t["buyin"] == 1000
        assert t["fee"] == 100
        assert t["status"] == "late_reg"
        assert t["entries"] == 87

    def test_name_only_id_hash(self):
        t = normalize.normalize_tournament({"site": "sunbet", "name": "Big One"})
        assert t["site_tournament_id"].startswith("nid-")


class TestQuality:
    def test_full_record_scores_100(self):
        t = {"site_tournament_id": "x", "name": "n", "buyin": 1000,
             "start_time": "2026-01-01T00:00:00+00:00", "status": "running",
             "field_size": 100, "entries": 120, "prize_pool": 50000}
        score, flags = quality.score_tournament(t)
        assert score == 100
        assert flags == []

    def test_missing_everything(self):
        t = {}
        score, flags = quality.score_tournament(t)
        assert score == 5  # 100 - (25 id + 25 buyin + 15 time + 10 field + 10 prize + 10 status)
        assert quality.CRITICAL_ID in flags
        assert quality.CRITICAL_BUYIN in flags

    def test_completed_without_prize_is_contradiction(self):
        t = {"site_tournament_id": "x", "name": "n", "buyin": 100,
             "start_time": "2026-01-01T00:00:00+00:00", "status": "completed",
             "field_size": 50, "entries": 50}
        score, flags = quality.score_tournament(t)
        assert quality.CONTRADICTION in flags
        assert score < 100

    def test_entries_less_than_field_contradiction(self):
        t = {"site_tournament_id": "x", "name": "n", "buyin": 100,
             "start_time": "2026-01-01T00:00:00+00:00", "status": "completed",
             "field_size": 200, "entries": 50, "prize_pool": 10000}
        _, flags = quality.score_tournament(t)
        assert quality.CONTRADICTION in flags

    def test_completeness_levels(self):
        assert quality.completeness_level(95) == "complete"
        assert quality.completeness_level(75) == "partial"
        assert quality.completeness_level(30) == "incomplete"
