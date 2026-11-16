"""Tests for bin/kaigi_google.py against a fake Google. Run: python3 -m unittest discover -s tests"""

import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import kaigi_google as g  # noqa: E402
from test_events import me  # noqa: E402  (the kaigi-events module)

TOKYO = ZoneInfo("Asia/Tokyo")
CLIENT = {"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "s3cret"}}


class FakeSecrets:
    def __init__(self):
        self.data = {}

    def store(self, account, token):
        self.data[account] = token
        return "keyring"

    def lookup(self, account):
        return self.data.get(account)

    def clear(self, account):
        self.data.pop(account, None)


class FakeGoogle:
    """Answers the token endpoint and the two Calendar API calls Kaigi makes."""

    def __init__(self, items=None, refresh_ok=True):
        self.calls = []
        self.items = items or []
        self.refresh_ok = refresh_ok
        self.verifier = None

    def request(self, method, url, data=None, headers=None):
        self.calls.append((method, url, data))
        if url == g.TOKEN_URL:
            if data["grant_type"] == "authorization_code":
                self.verifier = data["code_verifier"]
                assert data["code"] == "the-code" and data["client_secret"] == "s3cret"
                return 200, {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3599}
            if not self.refresh_ok:
                return 400, {"error": "invalid_grant"}
            assert data["refresh_token"] == "rt1"
            return 200, {"access_token": "at2", "expires_in": 3599}
        if url == g.REVOKE_URL:
            return 200, {}
        assert headers and headers["Authorization"].startswith("Bearer ")
        if url.endswith("/users/me/calendarList/primary"):
            return 200, {"id": "me@example.com", "primary": True}
        if "/users/me/calendarList" in url:
            return 200, {"items": [
                {"id": "me@example.com", "summary": "Me", "primary": True, "selected": True, "backgroundColor": "#4285f4"},
                {"id": "team@group.calendar.google.com", "summary": "Team", "selected": True, "backgroundColor": "#0b8043"},
                {"id": "hidden@group.calendar.google.com", "summary": "Hidden", "selected": False},
            ]}
        if "/events?" in url:
            cid = urllib.parse.unquote(url.split("/calendars/")[1].split("/events")[0])
            return 200, {"items": [i for i in self.items if i.get("_cal", "me@example.com") == cid]}
        return 404, {}


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.client_path = os.path.join(d, "google-client.json")
        self.accounts = os.path.join(d, "state", "google-accounts.json")
        self.config = os.path.join(d, "config.json")
        with open(self.client_path, "w") as fh:
            json.dump(CLIENT, fh)
        with open(self.config, "w") as fh:
            json.dump({"automaticEventJoin": True, "calendars": [{"name": "ics", "url": "https://x/y.ics"}]}, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def browser(self, code="the-code", state=None, error=None):
        """Stand-in for the user's browser: follow the consent URL straight to the redirect."""
        seen = {}

        def opener(url):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            seen.update({k: v[0] for k, v in q.items()})
            params = {"state": state if state is not None else seen["state"]}
            params.update({"error": error} if error else {"code": code})
            target = seen["redirect_uri"] + "/?" + urllib.parse.urlencode(params)
            threading.Thread(target=lambda: urllib.request.urlopen(target, timeout=5).read(), daemon=True).start()
        return opener, seen

    def login(self, fake, secrets, opener):
        return g.login("default", http_client=fake, opener=opener, secrets_store=secrets,
                       client_path=self.client_path, accounts_path=self.accounts, config_path=self.config, timeout=10)

    def test_full_login_with_pkce(self):
        fake, secrets = FakeGoogle(), FakeSecrets()
        opener, seen = self.browser()
        self.assertEqual(self.login(fake, secrets, opener), "me@example.com")
        self.assertEqual(seen["code_challenge_method"], "S256")
        self.assertEqual(seen["scope"], g.SCOPE)
        self.assertTrue(seen["redirect_uri"].startswith("http://127.0.0.1:"))
        self.assertEqual(seen["access_type"], "offline")
        expected = base64.urlsafe_b64encode(hashlib.sha256(fake.verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(seen["code_challenge"], expected)
        self.assertEqual(secrets.data["default"], "rt1")
        self.assertEqual(oct(os.stat(self.accounts).st_mode & 0o777), "0o600")
        self.assertEqual(g.read_json(self.accounts, {})["default"]["email"], "me@example.com")
        cfg = g.read_json(self.config, {})
        self.assertTrue(cfg["automaticEventJoin"])  # other settings kept
        self.assertEqual([c.get("type") for c in cfg["calendars"]], [None, "google"])
        # Logging in again does not add a second entry.
        opener, _ = self.browser()
        self.login(fake, secrets, opener)
        self.assertEqual(len(g.read_json(self.config, {})["calendars"]), 2)

    def test_state_mismatch_is_rejected(self):
        opener, _ = self.browser(state="forged")
        with self.assertRaisesRegex(g.GoogleError, "state mismatch"):
            self.login(FakeGoogle(), FakeSecrets(), opener)

    def test_denied_consent(self):
        opener, _ = self.browser(error="access_denied")
        with self.assertRaisesRegex(g.GoogleError, "access_denied"):
            self.login(FakeGoogle(), FakeSecrets(), opener)

    def test_missing_client(self):
        with self.assertRaises(g.ClientMissing):
            g.login("default", client_path=os.path.join(self.tmp.name, "nope.json"), opener=lambda u: None)

    def test_logout_removes_entry_and_token(self):
        fake, secrets = FakeGoogle(), FakeSecrets()
        opener, _ = self.browser()
        self.login(fake, secrets, opener)
        g.logout("default", http_client=fake, secrets_store=secrets, accounts_path=self.accounts, config_path=self.config,
                 cache_dir=self.tmp.name)
        self.assertNotIn("default", secrets.data)
        self.assertEqual([c.get("type") for c in g.read_json(self.config, {})["calendars"]], [None])
        self.assertIn((("POST", g.REVOKE_URL, {"token": "rt1"})), fake.calls)

    def test_setup_picks_newest_download(self):
        dl = os.path.join(self.tmp.name, "Downloads")
        os.makedirs(dl)
        old, new = os.path.join(dl, "client_secret_old.json"), os.path.join(dl, "client_secret_new.json")
        for p, t in ((old, 1000), (new, 2000)):
            with open(p, "w") as fh:
                json.dump(CLIENT, fh)
            os.utime(p, (t, t))
        dest = os.path.join(self.tmp.name, "cfg", "google-client.json")
        self.assertEqual(g.setup_client(None, dest, dl), new)
        self.assertEqual(oct(os.stat(dest).st_mode & 0o777), "0o600")
        with open(old, "w") as fh:
            json.dump({"installed": {"client_id": "not-google"}}, fh)
        with self.assertRaises(g.ClientMissing):
            g.setup_client(old, dest, dl)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client_path = os.path.join(self.tmp.name, "c.json")
        with open(self.client_path, "w") as fh:
            json.dump(CLIENT, fh)
        self.secrets = FakeSecrets()
        self.secrets.store("default", "rt1")
        self.ws = dt.datetime(2026, 11, 16, tzinfo=TOKYO)
        self.we = self.ws + dt.timedelta(days=2)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, fake, force=False, cal=None):
        return g.load("default", cal or {"calendarIds": []}, self.ws, self.we, 300, force, http_client=fake,
                      secrets_store=self.secrets, client_path=self.client_path, cache_dir=self.tmp.name)

    def test_selected_calendars_and_cache(self):
        fake = FakeGoogle(items=[{"id": "1", "_cal": "team@group.calendar.google.com", "summary": "t",
                                  "start": {"dateTime": "2026-11-16T10:00:00+09:00"}, "end": {"dateTime": "2026-11-16T11:00:00+09:00"}}])
        snap, err = self.load(fake)
        self.assertIsNone(err)
        self.assertEqual([c["id"] for c in snap["calendars"]], ["me@example.com", "team@group.calendar.google.com"])
        self.assertEqual(len(snap["events"]["team@group.calendar.google.com"]), 1)
        event_calls = [u for m, u, d in fake.calls if "/events?" in u]
        self.assertIn("singleEvents=true", event_calls[0])
        self.assertIn("timeMin=2026-11-15T15%3A00%3A00Z", event_calls[0])
        n = len(fake.calls)
        self.load(fake)  # fresh cache: no network
        self.assertEqual(len(fake.calls), n)
        self.load(fake, force=True)
        self.assertGreater(len(fake.calls), n)
        cache = os.path.join(self.tmp.name, g.cache_name("default"))
        self.assertEqual(oct(os.stat(cache).st_mode & 0o777), "0o600")
        with open(cache) as fh:
            self.assertNotIn("rt1", fh.read())

    def test_calendar_ids_filter(self):
        snap, _ = self.load(FakeGoogle(), cal={"calendarIds": ["hidden@group.calendar.google.com"]})
        self.assertEqual([c["id"] for c in snap["calendars"]], ["hidden@group.calendar.google.com"])

    def test_expired_grant_reports_auth_required_and_keeps_cache(self):
        self.load(FakeGoogle())
        snap, err = self.load(FakeGoogle(refresh_ok=False), force=True)
        self.assertIsInstance(err, g.AuthRequired)
        self.assertEqual(err.code, "auth_required")
        self.assertIsNotNone(snap)

    def test_not_signed_in(self):
        self.secrets.clear("default")
        snap, err = self.load(FakeGoogle())
        self.assertIsNone(snap)
        self.assertEqual(err.code, "auth_required")


class ConvertTests(unittest.TestCase):
    helpers = {"find_link": me.find_link, "add_authuser": me.add_authuser, "strip_html": me.strip_html,
               "clip": me.clip, "to_ms": me.to_ms, "max_title": 300, "max_text": 4000}

    def convert(self, items, filters=()):
        snap = {"calendars": [{"id": "me@example.com", "summary": "Me", "color": "#4285f4"}],
                "events": {"me@example.com": items}}
        return g.convert(snap, "me@example.com", "Google", self.helpers, [], [re.compile(f) for f in filters], TOKYO)

    def test_mapping(self):
        base = {"start": {"dateTime": "2026-11-16T10:00:00+09:00"}, "end": {"dateTime": "2026-11-16T10:30:00+09:00"}}
        items = [
            dict(base, id="a", summary="Sync", hangoutLink="https://meet.google.com/abc-defg-hij",
                 attendees=[{"email": "x@example.com", "responseStatus": "accepted"},
                            {"email": "me@example.com", "self": True, "responseStatus": "needsAction"}]),
            dict(base, id="b", summary="Zoom", location="https://zoom.us/j/1",
                 conferenceData={"entryPoints": [{"entryPointType": "phone", "uri": "tel:+1"},
                                                 {"entryPointType": "video", "uri": "https://us02web.zoom.us/j/999"}]},
                 attendees=[{"email": "me@example.com", "self": True, "responseStatus": "declined"}]),
            {"id": "c", "summary": "Holiday", "start": {"date": "2026-11-16"}, "end": {"date": "2026-11-17"}},
            dict(base, id="d", summary="Home", eventType="workingLocation"),
            dict(base, id="e", summary="Gone", status="cancelled"),
            dict(base, id="f", summary="Mine", attendees=[{"email": "o@example.com"}], organizer={"self": True}),
        ]
        got = {e["title"]: e for e in self.convert(items)}
        self.assertNotIn("Home", got)
        self.assertEqual(got["Sync"]["link"]["url"], "https://meet.google.com/abc-defg-hij?authuser=me%40example.com")
        self.assertEqual(got["Sync"]["participation"], "pending")
        self.assertEqual(got["Zoom"]["link"]["url"], "https://us02web.zoom.us/j/999")  # conference beats location
        self.assertEqual(got["Zoom"]["participation"], "declined")
        self.assertTrue(got["Holiday"]["allDay"])
        self.assertEqual(dt.datetime.fromtimestamp(got["Holiday"]["start"] / 1000, TOKYO).hour, 0)
        self.assertEqual(got["Gone"]["status"], "cancelled")
        self.assertEqual(got["Mine"]["participation"], "accepted")
        self.assertEqual(got["Sync"]["end"] - got["Sync"]["start"], 30 * 60 * 1000)
        self.assertEqual(got["Sync"]["color"], "#4285f4")

    def test_title_filters(self):
        base = {"start": {"dateTime": "2026-11-16T12:00:00+09:00"}, "end": {"dateTime": "2026-11-16T13:00:00+09:00"}}
        self.assertEqual(self.convert([dict(base, id="l", summary="Lunch")], filters=["^Lunch$"]), [])


if __name__ == "__main__":
    unittest.main()
