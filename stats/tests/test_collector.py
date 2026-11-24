"""Tests du collecteur de statistiques (stdlib)."""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import Store, make_server

KEY = "cle-de-test"
SUMMARY_EVENTS = [
    ("a" * 32, "install", "0.6.2", "linux"),
    ("b" * 32, "install", "0.6.2", "windows"),
    ("c" * 32, "install", "0.6.1", "windows"),
    ("a" * 32, "signature", "0.6.2", "linux"),
    ("a" * 32, "signature", "0.6.2", "linux"),
    ("b" * 32, "signature", "0.6.2", "windows"),
]


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "stats.sqlite3")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_install_is_deduplicated(self) -> None:
        self.assertTrue(self.store.record("a" * 32, "install", "0.6.2", "linux"))
        self.assertFalse(self.store.record("a" * 32, "install", "0.6.2", "linux"))
        self.assertTrue(
            self.store.record("b" * 32, "install", "0.6.2", "linux", day="2026-01-02")
        )

    def test_signatures_are_all_counted(self) -> None:
        for _ in range(3):
            self.assertTrue(self.store.record("a" * 32, "signature", "0.6.2", "linux"))
        summary = self.store.summary()
        self.assertEqual(summary["totals"]["signatures"], 3)

    def _record_all(self, events: list[tuple[str, str, str, str]]) -> None:
        for install, name, version, os_name in events:
            self.store.record(install, name, version, os_name)

    def test_summary_counts_unique_users(self) -> None:
        self._record_all(SUMMARY_EVENTS)
        summary = self.store.summary()
        self._assert_summary(summary)

    def _assert_summary(self, summary: dict) -> None:
        totals = summary["totals"]
        self.assertEqual(totals["installs"], 3)
        self.assertEqual(totals["signers"], 2)
        self.assertEqual(totals["signatures"], 3)
        self.assertEqual(len(summary["series"]), 30)
        self.assertEqual(summary["versions"][0]["installs"], 2)
        self.assertEqual(summary["platforms"][0]["installs"], 2)

    def test_empty_summary(self) -> None:
        totals = self.store.summary()["totals"]
        self.assertEqual(totals["installs"], 0)
        self.assertEqual(totals["signatures"], 0)


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "stats.sqlite3")
        self._start_http()

    def _start_http(self) -> None:
        options = {"ingest_key": KEY, "dashboard_password": "secret"}
        self.server = make_server(0, self.store, **options)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def _post_request(self, payload: dict, key: str) -> urllib.request.Request:
        headers = {"Content-Type": "application/json", "X-CheckMate-Key": key}
        body = json.dumps(payload).encode("utf-8")
        return urllib.request.Request(
            self.base + "/api/event", data=body, headers=headers, method="POST"
        )

    def post(self, payload: dict, key: str = KEY) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(self._post_request(payload, key)) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    def event(self, **overrides) -> dict:
        payload = {
            "install": "a" * 32,
            "event": "install",
            "version": "0.6.2",
            "os": "linux",
        }
        payload.update(overrides)
        return payload

    def test_valid_event_is_accepted_once(self) -> None:
        status, body = self.post(self.event())
        self.assertEqual(status, 202)
        self.assertFalse(body["duplicate"])

        status, body = self.post(self.event())
        self.assertEqual(status, 202)
        self.assertTrue(body["duplicate"])

    def test_bad_key_is_rejected(self) -> None:
        status, _ = self.post(self.event(), key="faux")
        self.assertEqual(status, 401)

    def test_bad_payload_is_rejected(self) -> None:
        for payload in (
            self.event(event="daily"),
            self.event(event="inconnu"),
            self.event(install="pas-un-hex"),
            self.event(version=""),
            self.event(os="beos"),
        ):
            status, _ = self.post(payload)
            self.assertEqual(status, 400, payload)

    def _authorized_request(self, path: str) -> urllib.request.Request:
        token = base64.b64encode(b"checkmate:secret").decode("ascii")
        headers = {"Authorization": f"Basic {token}"}
        return urllib.request.Request(self.base + path, headers=headers)

    def test_dashboard_requires_password(self) -> None:
        with urllib.request.urlopen(self.base + "/health") as response:
            self.assertEqual(response.status, 200)
        self._assert_unauthorized("/")
        with urllib.request.urlopen(self._authorized_request("/")) as response:
            self.assertIn("CheckMate", response.read().decode("utf-8"))

    def _assert_unauthorized(self, path: str) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self.base + path)
        self.assertEqual(raised.exception.code, 401)

    def test_stats_endpoint(self) -> None:
        self.post(self.event())
        token = base64.b64encode(b"checkmate:secret").decode("ascii")
        request = urllib.request.Request(
            self.base + "/api/stats", headers={"Authorization": f"Basic {token}"}
        )
        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read())
        self.assertEqual(data["totals"]["installs"], 1)


if __name__ == "__main__":
    unittest.main()
