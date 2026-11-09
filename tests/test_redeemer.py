#!/usr/bin/env python3
"""Offline unit tests: no network, no account needed. Run: python3 tests/test_redeemer.py"""

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wos-gift-codes" / "scripts"))

import redeemer  # noqa: E402


class Signing(unittest.TestCase):
    def test_signature_is_md5_of_sorted_pairs_plus_client_key(self):
        payload = {"fid": "12345678", "kid": "4351", "cdk": "GOGOWOS", "time": "1700000000"}
        expected = hashlib.md5(
            (f"cdk=GOGOWOS&fid=12345678&kid=4351&time=1700000000{redeemer.SECRET}").encode()
        ).hexdigest()
        self.assertEqual(redeemer.sign(payload), expected)

    def test_key_order_does_not_change_signature(self):
        a = {"fid": "1", "kid": "2", "cdk": "X", "time": "3"}
        b = {"time": "3", "cdk": "X", "kid": "2", "fid": "1"}
        self.assertEqual(redeemer.sign(a), redeemer.sign(b))


class Classify(unittest.TestCase):
    def test_known_statuses(self):
        cases = {
            ("SUCCESS", 20000): "SUCCESS",
            ("RECEIVED", 40008): "RECEIVED",
            ("TIME ERROR", 40007): "TIME ERROR",
            ("CDK NOT FOUND", 40014): "CDK NOT FOUND",
            ("USED", 40005): "USED",
            ("TOO FREQUENT", 40019): "TOO FREQUENT",
            # what a wrong state actually returns in practice
            ("USER INFO ERROR.", 40020): "USER INFO ERROR",
        }
        for (msg, err), expected in cases.items():
            with self.subTest(msg=msg):
                self.assertEqual(redeemer.classify({"msg": msg, "err_code": err}), expected)

    def test_role_not_exist(self):
        self.assertEqual(
            redeemer.classify({"msg": "role not exist", "err_code": 40001}), "ROLE NOT EXIST"
        )

    def test_unknown_is_passed_through(self):
        self.assertEqual(redeemer.classify({"msg": "SOMETHING NEW", "err_code": 1}), "SOMETHING NEW")


class Dedupe(unittest.TestCase):
    def test_collect_codes_dedupes_and_keeps_order(self):
        original_api, original_scrape = redeemer.fetch_codes_from_api, redeemer.fetch_codes_from_scrape
        redeemer.fetch_codes_from_api = lambda: ["AAA111", "BBB222"]
        redeemer.fetch_codes_from_scrape = lambda: ["BBB222", "CCC333"]
        try:
            self.assertEqual(redeemer.collect_codes(None), ["AAA111", "BBB222", "CCC333"])
        finally:
            redeemer.fetch_codes_from_api, redeemer.fetch_codes_from_scrape = original_api, original_scrape


if __name__ == "__main__":
    unittest.main(verbosity=2)
