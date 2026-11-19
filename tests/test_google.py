"""Tests for bin/kaigi_google.py against a fake Google. Run: python3 -m unittest discover -s tests"""

import base64
import datetime as dt
import hashlib
import json
import os
import re
import signal
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
# Tests must not pick up a client shipped in bin/.
g.BUNDLED_CLIENT_PATH = os.path.join(ROOT, "tests", "no-bundled-client.json")
CLIENT = {"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "s3cret"}}


class FakeSecrets:
    def __init__(self, clear_ok=True):
        self.data = {}
        self.clear_ok = clear_ok

    def store(self, account, token):
        self.data[account] = token
        return "keyring"

    def lookup(self, account):
        return self.data.get(account)

    def clear(self, account):
        if not self.clear_ok:
            return False
        self.data.pop(account, None)
        return True


class FakeGoogle:
    """Answers the token endpoint and the two Calendar API calls Kaigi makes."""

    def __init__(self, items=None, refresh_ok=True, revoke=(200, {})):
        self.calls = []
        self.revoke = revoke
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
            if self.revoke is None:
                raise OSError("network down")
            return self.revoke
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

    def test_a_stop_request_after_the_browser_came_back_does_not_strand_the_token(self):
        # The shell sends SIGTERM to replace a sign-in that is waiting for the
        # browser. Arriving after the callback, it must not end the sign-in
        # between storing the token and listing the account.
        stopped = []
        previous = signal.signal(signal.SIGTERM, lambda *_: stopped.append(True))
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        ours = signal.getsignal(signal.SIGTERM)

        class StoppedWhileStoring(FakeSecrets):
            def store(self, account, token):
                where = super().store(account, token)
                os.kill(os.getpid(), signal.SIGTERM)
                return where

        fake, secrets = FakeGoogle(), StoppedWhileStoring()
        opener, _ = self.browser()
        self.assertEqual(self.login(fake, secrets, opener), "me@example.com")
        self.assertEqual(stopped, [])
        self.assertEqual(secrets.data["default"], "rt1")
        self.assertEqual(g.read_json(self.accounts, {})["default"]["email"], "me@example.com")
        self.assertEqual([c.get("type") for c in g.read_json(self.config, {})["calendars"]], [None, "google"])
        # Before the browser comes back, and after the sign-in, stopping works as usual.
        self.assertIs(signal.getsignal(signal.SIGTERM), ours)
        os.kill(os.getpid(), signal.SIGTERM)
        self.assertEqual(stopped, [True])

    def test_add_account_auto_keys_by_email_and_leaves_profile_automatic(self):
        chrome = os.path.join(self.tmp.name, "cfg", "google-chrome")
        os.makedirs(chrome)
        with open(os.path.join(chrome, "Local State"), "w") as fh:
            json.dump({"profile": {"info_cache": {"Default": {"user_name": "other@example.com"},
                                                  "Profile 2": {"user_name": "Me@Example.com"}}}}, fh)
        old_env = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.tmp.name, "cfg")
        try:
            fake, secrets = FakeGoogle(), FakeSecrets()
            opener, _ = self.browser()
            g.login("auto", http_client=fake, opener=opener, secrets_store=secrets, client_path=self.client_path,
                    accounts_path=self.accounts, config_path=self.config, timeout=10)
            self.assertIn("me@example.com", secrets.data)
            entry = [c for c in g.read_json(self.config, {})["calendars"] if c.get("type") == "google"][0]
            self.assertEqual(entry["account"], "me@example.com")
            # The profile is found when meetings open, so it can follow the account.
            self.assertNotIn("chromeProfile", entry)
            self.assertEqual(g.resolve_chrome_profile("me@example.com", "", g.chrome_state())[:2], ("Profile 2", "primary"))
            # Adding the same address again reuses its key instead of duplicating it.
            opener, _ = self.browser()
            g.login("auto", http_client=fake, opener=opener, secrets_store=secrets, client_path=self.client_path,
                    accounts_path=self.accounts, config_path=self.config, timeout=10)
            self.assertEqual(list(g.read_json(self.accounts, {}).keys()), ["me@example.com"])
        finally:
            if old_env is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_env

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

    def logout_with(self, fake, secrets):
        g.logout("default", http_client=fake, secrets_store=secrets, accounts_path=self.accounts,
                 config_path=self.config, cache_dir=self.tmp.name)

    def signed_in(self, secrets):
        self.login(FakeGoogle(), secrets, self.browser()[0])
        cache = os.path.join(self.tmp.name, g.cache_name("default"))
        with open(cache, "w") as fh:
            fh.write("{}")
        return cache

    def test_logout_keeps_the_account_when_nothing_could_be_undone(self):
        secrets = FakeSecrets()
        cache = self.signed_in(secrets)
        secrets.clear_ok = False
        for revoke in (None, (503, {}), (400, {"error": "invalid_request"})):
            with self.assertRaises(g.SignOutIncomplete):
                self.logout_with(FakeGoogle(revoke=revoke), secrets)
            self.assertEqual(secrets.data.get("default"), "rt1")
            self.assertIn("default", g.read_json(self.accounts, {}))
            self.assertIn("google", [c.get("type") for c in g.read_json(self.config, {})["calendars"]])
            self.assertTrue(os.path.exists(cache))

    def test_logout_without_revocation_still_removes_the_local_token(self):
        secrets = FakeSecrets()
        cache = self.signed_in(secrets)
        with self.assertRaises(g.RevokeUnconfirmed):
            self.logout_with(FakeGoogle(revoke=None), secrets)
        self.assertNotIn("default", secrets.data)
        self.assertNotIn("default", g.read_json(self.accounts, {}))
        self.assertFalse(os.path.exists(cache))

    def test_logout_accepts_an_already_invalid_token_or_a_kept_dead_one(self):
        secrets = FakeSecrets()
        self.signed_in(secrets)
        self.logout_with(FakeGoogle(revoke=(400, {"error": "invalid_token"})), secrets)
        self.assertNotIn("default", g.read_json(self.accounts, {}))
        # Revoked but the keyring refused: the token is dead, so the account goes.
        secrets = FakeSecrets()
        self.signed_in(secrets)
        secrets.clear_ok = False
        self.logout_with(FakeGoogle(), secrets)
        self.assertNotIn("default", g.read_json(self.accounts, {}))

    def test_secrets_clear_reports_a_failing_keyring(self):
        tool = os.path.join(self.tmp.name, "secret-tool")
        for code, expected in ((0, True), (1, False)):
            with open(tool, "w") as fh:
                fh.write(f"#!/bin/sh\nexit {code}\n")
            os.chmod(tool, 0o755)
            store = g.Secrets(state_dir=self.tmp.name, tool=tool)
            self.assertIs(store.clear("default"), expected)

    def test_bundled_client_is_the_fallback(self):
        bundled = os.path.join(self.tmp.name, "bundled.json")
        with open(bundled, "w") as fh:
            json.dump({"installed": {"client_id": "999-bundled.apps.googleusercontent.com", "client_secret": "x"}}, fh)
        old = g.BUNDLED_CLIENT_PATH
        g.BUNDLED_CLIENT_PATH = bundled
        try:
            missing = os.path.join(self.tmp.name, "none.json")
            self.assertEqual(g.load_client(missing)["client_id"], "999-bundled.apps.googleusercontent.com")
            self.assertEqual(g.status(missing, self.accounts)["clientSource"], "bundled")
            # A client the user imported wins over the bundled one.
            self.assertEqual(g.load_client(self.client_path)["client_id"], "123-abc.apps.googleusercontent.com")
            self.assertEqual(g.status(self.client_path, self.accounts)["clientSource"], "user")
            # setup validates the file it was given, never the bundled one.
            with self.assertRaises(g.ClientMissing):
                g.setup_client(missing, os.path.join(self.tmp.name, "dest.json"), self.tmp.name)
        finally:
            g.BUNDLED_CLIENT_PATH = old

    def test_scopes_are_the_narrow_read_only_ones(self):
        self.assertEqual(g.SCOPE.split(), ["https://www.googleapis.com/auth/calendar.events.readonly",
                                           "https://www.googleapis.com/auth/calendar.calendarlist.readonly"])

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
        newest = os.path.join(dl, "123-abc.apps.googleusercontent.com.json")
        with open(newest, "w") as fh:
            json.dump(CLIENT, fh)
        os.utime(newest, (3000, 3000))
        self.assertEqual(g.setup_client(None, dest, dl), newest)
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
               "clip": me.clip, "to_ms": me.to_ms, "max_title": 300, "max_text": 4000,
               "notes_text": me.notes_text, "attendee_list": me.attendee_list}

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
        self.assertEqual(got["Sync"]["calendarId"], "me@example.com")
        self.assertEqual(got["Sync"]["attendeeCount"], 2)
        self.assertEqual(got["Sync"]["attendees"], [
            {"name": "x@example.com", "response": "accepted", "self": False, "organizer": False},
            {"name": "me@example.com", "response": "pending", "self": True, "organizer": False}])

    def test_notes_are_plain_text(self):
        base = {"start": {"dateTime": "2026-11-16T10:00:00+09:00"}, "end": {"dateTime": "2026-11-16T10:30:00+09:00"}}
        got = self.convert([dict(base, id="n", summary="N", description="<p>Agenda</p><br><br><br>Item &amp; more")])
        self.assertEqual(got[0]["notes"], "Agenda\n\nItem & more")

    def test_title_filters(self):
        base = {"start": {"dateTime": "2026-11-16T12:00:00+09:00"}, "end": {"dateTime": "2026-11-16T13:00:00+09:00"}}
        self.assertEqual(self.convert([dict(base, id="l", summary="Lunch")], filters=["^Lunch$"]), [])



class ChromeProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "google-chrome")
        os.makedirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, info_cache, accounts, last_used="Default", active=()):
        with open(os.path.join(self.root, "Local State"), "w") as fh:
            json.dump({"profile": {"info_cache": info_cache, "last_used": last_used,
                                   "last_active_profiles": list(active)}}, fh)
        for folder, emails in accounts.items():
            os.makedirs(os.path.join(self.root, folder), exist_ok=True)
            with open(os.path.join(self.root, folder, "Preferences"), "w") as fh:
                json.dump({"account_info": [{"email": e} for e in emails]}, fh)
        return g.chrome_state(self.tmp.name)

    def test_primary_then_signed_in_then_none(self):
        state = self.write({"Default": {"user_name": "a@x.com", "name": "Home"}, "Profile 2": {"user_name": "Work@X.com"}},
                           {"Default": ["a@x.com", "b@x.com", "work@x.com"], "Profile 2": ["work@x.com"]})
        self.assertEqual(state["profiles"][0]["accounts"], ["a@x.com", "b@x.com", "work@x.com"])
        # The profile Chrome is signed in to wins over one where it is only signed in to Google.
        self.assertEqual(g.resolve_chrome_profile("work@x.com", "", state), ("Profile 2", "primary", False))
        self.assertEqual(g.resolve_chrome_profile("B@x.com", "", state), ("Default", "signedIn", False))
        self.assertEqual(g.resolve_chrome_profile("c@x.com", "", state), ("", "none", False))
        self.assertEqual(g.chrome_profiles(state)[0], {"dir": "Default", "name": "Home", "email": "a@x.com",
                                                       "browser": "google-chrome"})

    def test_signed_in_prefers_the_most_recently_used_profile(self):
        state = self.write({"Default": {}, "Profile 3": {}}, {"Default": ["b@x.com"], "Profile 3": ["b@x.com"]},
                           last_used="Profile 3")
        self.assertEqual(g.resolve_chrome_profile("b@x.com", "", state)[0], "Profile 3")

    def test_a_stored_profile_is_kept_while_it_has_the_account(self):
        state = self.write({"Default": {"user_name": "a@x.com"}, "Profile 2": {"user_name": "b@x.com"}},
                           {"Default": ["a@x.com", "b@x.com"], "Profile 2": ["b@x.com"]})
        self.assertEqual(g.resolve_chrome_profile("b@x.com", "Default", state), ("Default", "config", False))
        # The account moved out of the stored profile, or the profile is gone: back to automatic.
        self.assertEqual(g.resolve_chrome_profile("a@x.com", "Profile 2", state), ("Default", "primary", True))
        self.assertEqual(g.resolve_chrome_profile("a@x.com", "Profile 9", state), ("Default", "primary", True))
        self.assertEqual(g.resolve_chrome_profile("z@x.com", "Profile 9", state), ("", "none", True))
        # A profile with no accounts recorded keeps the choice.
        state = self.write({"Default": {"user_name": "a@x.com"}, "Profile 5": {}}, {"Default": ["a@x.com"]})
        self.assertEqual(g.resolve_chrome_profile("a@x.com", "Profile 5", state), ("Profile 5", "config", False))
        # Without Chrome's files there is nothing to check, so the choice stands.
        self.assertEqual(g.resolve_chrome_profile("a@x.com", "Profile 9", {"profiles": []}), ("Profile 9", "config", False))

    def test_odd_folders_and_unreadable_preferences_are_tolerated(self):
        state = self.write({"Default": {"user_name": "a@x.com"}, "../evil": {"user_name": "e@x.com"}, "Profile 4": "x"}, {})
        self.assertEqual([p["dir"] for p in state["profiles"]], ["Default"])
        self.assertEqual(state["profiles"][0]["accounts"], ["a@x.com"])

if __name__ == "__main__":
    unittest.main()
