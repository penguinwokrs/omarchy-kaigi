"""Tests for bin/kaigi-events. Run: python3 -m unittest discover -s tests"""

import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["TZ"] = "Asia/Tokyo"
loader = importlib.machinery.SourceFileLoader("kaigi_events", os.path.join(ROOT, "bin", "kaigi-events"))
spec = importlib.util.spec_from_loader("kaigi_events", loader)
me = importlib.util.module_from_spec(spec)
loader.exec_module(me)

TOKYO = ZoneInfo("Asia/Tokyo")
NY = ZoneInfo("America/New_York")
EMAIL = "me@example.com"


def cal(*events):
    body = "\r\n".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:test\r\n{body}\r\nEND:VCALENDAR\r\n"


def vevent(**props):
    lines = ["BEGIN:VEVENT"]
    for k, v in props.items():
        k = k.replace("__", ";").replace("_", "-")
        for item in v if isinstance(v, list) else [v]:
            lines.append(f"{k}:{item}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def run(text, start, days=2, emails=(EMAIL,), filters=(), custom=()):
    ws = start.replace(hour=0, minute=0, second=0, microsecond=0)
    import re
    return me.collect(text, "Test", set(emails), [re.compile(c) for c in custom],
                      [re.compile(f) for f in filters], ws, ws + dt.timedelta(days=days))


def starts(events, tz=TOKYO):
    return [dt.datetime.fromtimestamp(e["start"] / 1000, tz).strftime("%Y-%m-%d %H:%M") for e in events]


class ParseTests(unittest.TestCase):
    def test_folding_escaping_and_tzid(self):
        text = cal("BEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Weekly\\, sync\r\n  part two\r\n"
                   "DTSTART;TZID=Asia/Tokyo:20261116T100000\r\nDTEND;TZID=Asia/Tokyo:20261116T103000\r\nEND:VEVENT")
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(ev[0]["title"], "Weekly, sync part two")
        self.assertEqual(starts(ev), ["2026-11-16 10:00"])
        self.assertEqual(ev[0]["end"] - ev[0]["start"], 30 * 60 * 1000)

    def test_utc_and_floating(self):
        text = cal(vevent(UID="u", SUMMARY="utc", DTSTART="20261116T010000Z", DTEND="20261116T020000Z"),
                   vevent(UID="f", SUMMARY="floating", DTSTART="20261116T150000", DURATION="PT45M"))
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(starts(ev), ["2026-11-16 10:00", "2026-11-16 15:00"])
        self.assertEqual(ev[1]["end"] - ev[1]["start"], 45 * 60 * 1000)

    def test_all_day(self):
        text = cal(vevent(UID="d", SUMMARY="Holiday", DTSTART__VALUE_DATE="20261116", DTEND__VALUE_DATE="20261117"))
        text = text.replace("DTSTART;VALUE-DATE", "DTSTART;VALUE=DATE").replace("DTEND;VALUE-DATE", "DTEND;VALUE=DATE")
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertTrue(ev[0]["allDay"])
        self.assertEqual(starts(ev), ["2026-11-16 00:00"])

    def test_valarm_does_not_leak_into_event(self):
        text = cal("BEGIN:VEVENT\r\nUID:x\r\nSUMMARY:Real\r\nDTSTART:20261116T010000Z\r\nDTEND:20261116T020000Z\r\n"
                   "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Reminder\r\nTRIGGER:-PT10M\r\nEND:VALARM\r\nEND:VEVENT")
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "Real")


class RecurrenceTests(unittest.TestCase):
    def test_weekly_byday_with_exdate_and_override(self):
        text = cal(
            vevent(UID="r1", SUMMARY="Standup", DTSTART__TZID_Asia_Tokyo="20260105T093000",
                   DTEND__TZID_Asia_Tokyo="20260105T094500", RRULE="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
                   EXDATE__TZID_Asia_Tokyo="20261117T093000"),
            vevent(UID="r1", SUMMARY="Standup (moved)", RECURRENCE__ID__TZID_Asia_Tokyo="20261118T093000",
                   DTSTART__TZID_Asia_Tokyo="20261118T110000", DTEND__TZID_Asia_Tokyo="20261118T111500"),
        )
        text = text.replace("TZID-Asia-Tokyo", "TZID=Asia/Tokyo").replace("RECURRENCE-ID-", "RECURRENCE-ID;").replace("RECURRENCE;ID;", "RECURRENCE-ID;")
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO), days=3)
        self.assertEqual(starts(ev), ["2026-11-16 09:30", "2026-11-18 11:00"])
        self.assertEqual(ev[1]["title"], "Standup (moved)")

    def test_cancelled_override(self):
        text = cal(
            vevent(UID="c", SUMMARY="1on1", DTSTART="20261102T010000Z", DTEND="20261102T013000Z", RRULE="FREQ=WEEKLY"),
            vevent(UID="c", SUMMARY="1on1", STATUS="CANCELLED", DTSTART="20261116T010000Z", DTEND="20261116T013000Z")
            .replace("BEGIN:VEVENT", "BEGIN:VEVENT\r\nRECURRENCE-ID:20261116T010000Z"),
        )
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["status"], "cancelled")

    def test_count_and_until(self):
        text = cal(vevent(UID="n", SUMMARY="count", DTSTART="20261113T010000Z", DTEND="20261113T020000Z", RRULE="FREQ=DAILY;COUNT=4"),
                   vevent(UID="u", SUMMARY="until", DTSTART="20261110T030000Z", DTEND="20261110T040000Z", RRULE="FREQ=DAILY;UNTIL=20261116T030000Z"))
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO), days=2)
        self.assertEqual(sorted((e["title"], s) for e, s in zip(ev, starts(ev))),
                         [("count", "2026-11-16 10:00"), ("until", "2026-11-16 12:00")])

    def test_monthly_nth_weekday_and_last_day(self):
        text = cal(vevent(UID="m", SUMMARY="2nd Tue", DTSTART="20260113T000000Z", DTEND="20260113T010000Z", RRULE="FREQ=MONTHLY;BYDAY=2TU"),
                   vevent(UID="l", SUMMARY="last day", DTSTART="20260131T000000Z", DTEND="20260131T010000Z", RRULE="FREQ=MONTHLY;BYMONTHDAY=-1"))
        ev = run(text, dt.datetime(2026, 11, 1, tzinfo=TOKYO), days=30)
        self.assertEqual(starts(ev), ["2026-11-10 09:00", "2026-11-30 09:00"])

    def test_interval_and_yearly(self):
        text = cal(vevent(UID="b", SUMMARY="biweekly", DTSTART="20261102T010000Z", DTEND="20261102T020000Z", RRULE="FREQ=WEEKLY;INTERVAL=2"),
                   vevent(UID="y", SUMMARY="anniv", DTSTART="20201116T010000Z", DTEND="20201116T020000Z", RRULE="FREQ=YEARLY"))
        ev = run(text, dt.datetime(2026, 11, 9, tzinfo=TOKYO), days=14)
        self.assertEqual(sorted((e["title"], s) for e, s in zip(ev, starts(ev))),
                         [("anniv", "2026-11-16 10:00"), ("biweekly", "2026-11-16 10:00")])

    def test_dst_keeps_wall_clock(self):
        # 9:00 New York every day across the 2026-11-01 DST change.
        text = cal("BEGIN:VEVENT\r\nUID:dst\r\nSUMMARY:NY\r\nDTSTART;TZID=America/New_York:20261029T090000\r\n"
                   "DTEND;TZID=America/New_York:20261029T093000\r\nRRULE:FREQ=DAILY\r\nEND:VEVENT")
        ev = run(text, dt.datetime(2026, 10, 31, tzinfo=TOKYO), days=4)
        ny = starts(ev, NY)
        self.assertTrue(all(s.endswith("09:00") for s in ny), ny)
        utc_hours = {dt.datetime.fromtimestamp(e["start"] / 1000, dt.timezone.utc).hour for e in ev}
        self.assertEqual(utc_hours, {13, 14})

    def test_old_daily_series_is_fast_forwarded(self):
        text = cal(vevent(UID="old", SUMMARY="old", DTSTART="20000101T000000Z", DTEND="20000101T001000Z", RRULE="FREQ=DAILY"))
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO), days=1)
        self.assertEqual(starts(ev), ["2026-11-16 09:00"])

    def test_ongoing_from_yesterday_is_included(self):
        text = cal(vevent(UID="o", SUMMARY="long", DTSTART="20261115T140000Z", DTEND="20261116T020000Z"))
        self.assertEqual(len(run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))), 1)


class AttendeeTests(unittest.TestCase):
    def test_partstat_for_own_address(self):
        base = dict(DTSTART="20261116T010000Z", DTEND="20261116T020000Z")
        text = cal(vevent(UID="1", SUMMARY="declined", ATTENDEE__PARTSTAT_DECLINED="mailto:me@example.com", **base),
                   vevent(UID="2", SUMMARY="tentative", ATTENDEE__PARTSTAT_TENTATIVE="mailto:ME@example.com", **base),
                   vevent(UID="3", SUMMARY="pending", ATTENDEE__PARTSTAT_NEEDS_ACTION="mailto:me@example.com", **base),
                   vevent(UID="4", SUMMARY="personal", **base))
        text = (text.replace("PARTSTAT-DECLINED", "PARTSTAT=DECLINED").replace("PARTSTAT-TENTATIVE", "PARTSTAT=TENTATIVE")
                .replace("PARTSTAT-NEEDS-ACTION", "PARTSTAT=NEEDS-ACTION"))
        got = {e["title"]: (e["participation"], e["hasAttendees"]) for e in run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))}
        self.assertEqual(got, {"declined": ("declined", True), "tentative": ("tentative", True),
                               "pending": ("pending", True), "personal": ("accepted", False)})

    def test_details_for_the_popup(self):
        base = dict(DTSTART="20261116T010000Z", DTEND="20261116T020000Z")
        text = cal(vevent(UID="1", SUMMARY="Review", DESCRIPTION="Agenda\\nItem",
                          ATTENDEE__CN_Ana__PARTSTAT_ACCEPTED="mailto:ana@example.com",
                          ATTENDEE__PARTSTAT_NEEDS_ACTION="mailto:me@example.com",
                          ORGANIZER__CN_Ana="mailto:ana@example.com", **base))
        text = (text.replace("PARTSTAT-ACCEPTED", "PARTSTAT=ACCEPTED")
                .replace("PARTSTAT-NEEDS-ACTION", "PARTSTAT=NEEDS-ACTION").replace("CN-Ana", "CN=Ana"))
        [e] = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(e["notes"], "Agenda\nItem")
        self.assertEqual(e["attendeeCount"], 2)
        self.assertEqual(e["attendees"], [
            {"name": "Ana", "response": "accepted", "self": False, "organizer": True},
            {"name": "me@example.com", "response": "pending", "self": True, "organizer": False}])

    def test_feed_email_from_google_url(self):
        url = "https://calendar.google.com/calendar/ical/me%40example.com/private-abc/basic.ics"
        self.assertEqual(me.feed_email(url), "me@example.com")
        self.assertIsNone(me.feed_email("https://calendar.google.com/calendar/ical/abc%40group.calendar.google.com/private-x/basic.ics"))


class LinkTests(unittest.TestCase):
    def link(self, fields, custom=()):
        import re
        return me.find_link(fields, [re.compile(c) for c in custom])

    def test_every_pattern_compiles(self):
        with open(os.path.join(ROOT, "bin", "services.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(len(me.services()), len(doc["services"]))

    def test_known_services(self):
        cases = {
            "https://meet.google.com/abc-defg-hij": "meet",
            "https://us02web.zoom.us/j/123456789?pwd=abc-DEF_1.2": "zoom",
            "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc%40thread.v2/0?context=x": "teams",
            "https://acme.webex.com/meet/jdoe": "webex",
            "https://meet.jit.si/MyRoom": "jitsi",
            "https://app.slack.com/huddle/T123/C456": "slack",
            "https://whereby.com/room": "whereby",
            "https://www.youtube.com/watch?v=x": "youtube",
        }
        for url, sid in cases.items():
            with self.subTest(url=url):
                got = self.link([("notes", f"Join: {url} now")])
                self.assertEqual(got["service"], sid)
                self.assertEqual(got["url"], url)

    def test_source_priority_and_tier(self):
        got = self.link([("conference", "https://meet.google.com/aaa-bbbb-ccc"), ("location", "https://zoom.us/j/1")])
        self.assertEqual(got["service"], "meet")
        got = self.link([("notes", "https://youtu.be/x then https://zoom.us/j/99")])
        self.assertEqual(got["service"], "zoom")

    def test_redirect_unwrapping(self):
        text = "https://www.google.com/url?q=https%3A%2F%2Fmeet.google.com%2Fabc-defg-hij&sa=D"
        self.assertEqual(self.link([("notes", text)])["url"], "https://meet.google.com/abc-defg-hij")
        safe = "https://nam02.safelinks.protection.outlook.com/?url=https%3A%2F%2Fzoom.us%2Fj%2F42&data=x"
        self.assertEqual(self.link([("notes", safe)])["url"], "https://zoom.us/j/42")

    def test_html_notes_and_custom(self):
        self.assertEqual(self.link([("htmlNotes", me.strip_html('<a href="https://meet.jit.si/x">join</a>'))])["service"], "jitsi")
        self.assertEqual(self.link([("notes", "https://intra.example/rooms/7")], custom=[r"https://intra\.example/rooms/\d+"])["service"], "other")
        self.assertIsNone(self.link([("notes", "no links here")]))

    def test_html_description_through_event(self):
        text = cal(vevent(UID="h", SUMMARY="h", DTSTART="20261116T010000Z", DTEND="20261116T020000Z",
                          DESCRIPTION='<a href="https://meet.jit.si/Room">Join</a>'))
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(ev[0]["link"]["url"], "https://meet.jit.si/Room")

    def test_google_meet_authuser(self):
        text = cal(vevent(UID="g", SUMMARY="g", DTSTART="20261116T010000Z", DTEND="20261116T020000Z",
                          X_GOOGLE_CONFERENCE="https://meet.google.com/abc-defg-hij"))
        ev = run(text, dt.datetime(2026, 11, 16, tzinfo=TOKYO))
        self.assertEqual(ev[0]["link"]["url"], "https://meet.google.com/abc-defg-hij?authuser=me%40example.com")

    def test_authuser_only_for_google_meet_host(self):
        add = me.add_authuser
        self.assertEqual(add("https://meet.google.com/abc-defg-hij", "a@example.com"),
                         "https://meet.google.com/abc-defg-hij?authuser=a%40example.com")
        self.assertEqual(add("https://meet.google.com/abc?pli=1#x", "a@example.com"),
                         "https://meet.google.com/abc?pli=1&authuser=a%40example.com#x")
        # Already chosen: left alone.
        self.assertEqual(add("https://meet.google.com/abc?authuser=1", "a@example.com"),
                         "https://meet.google.com/abc?authuser=1")
        for url in ("https://meet.google.com.evil.example/abc",
                    "https://evil.example/meet.google.com/abc",
                    "https://evil.example/?next=https://meet.google.com/abc",
                    "https://meet.google.com@evil.example/abc",
                    "https://user:pw@meet.google.com/abc",
                    "https://meet.google.com:8443/abc",
                    "https://meet.google.com:bad/abc",
                    "http://meet.google.com/abc",
                    "https://xmeet.google.com/abc"):
            self.assertEqual(add(url, "a@example.com"), url, url)
        self.assertEqual(add("https://meet.google.com/abc", None), "https://meet.google.com/abc")


class MainTests(unittest.TestCase):
    def test_local_file_calendar_and_filters(self):
        with tempfile.TemporaryDirectory() as d:
            ics = os.path.join(d, "a.ics")
            with open(ics, "w") as fh:
                fh.write(cal(vevent(UID="1", SUMMARY="Keep", DTSTART="20261116T010000Z", DTEND="20261116T020000Z"),
                             vevent(UID="2", SUMMARY="Lunch", DTSTART="20261116T030000Z", DTEND="20261116T040000Z")))
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w") as fh:
                json.dump({"calendars": [{"name": "Local", "path": ics, "chromeProfile": "Profile 3"}],
                           "chromeProfile": "Default", "filterEventRegexes": ["^Lunch$"]}, fh)
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                me.main(["--config", cfg, "--now", str(int(dt.datetime(2026, 11, 16, 8, tzinfo=TOKYO).timestamp() * 1000))])
            out = json.loads(buf.getvalue())
            self.assertTrue(out["configured"])
            self.assertEqual([e["title"] for e in out["events"]], ["Keep"])
            self.assertEqual(out["events"][0]["browserProfile"], "Profile 3")

    def test_pending_auto_join_setting(self):
        cal_entry = {"name": "Local"}
        self.assertTrue(me.pending_auto_join(cal_entry))
        self.assertFalse(me.pending_auto_join({"pendingAutoJoin": False}))
        self.assertTrue(me.pending_auto_join({"pendingAutoJoin": "no"}))  # junk falls back to the default
        team_off = {"pendingAutoJoin": {"team": False, "bad": "x"}}
        self.assertFalse(me.pending_auto_join(team_off, "team"))
        self.assertTrue(me.pending_auto_join(team_off, "me@example.com"))
        self.assertEqual(me.pending_auto_join_map(team_off), {"team": False})
        self.assertEqual(me.pending_auto_join_map({"pendingAutoJoin": False}), {})

    def test_feed_with_pending_auto_join_off(self):
        with tempfile.TemporaryDirectory() as d:
            ics = os.path.join(d, "a.ics")
            with open(ics, "w") as fh:
                fh.write(cal(vevent(UID="1", SUMMARY="Invite", DTSTART="20261116T010000Z", DTEND="20261116T020000Z")))
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w") as fh:
                json.dump({"calendars": [{"name": "Off", "path": ics, "pendingAutoJoin": False},
                                         {"name": "On", "path": ics}]}, fh)
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                me.main(["--config", cfg, "--now", str(int(dt.datetime(2026, 11, 16, 8, tzinfo=TOKYO).timestamp() * 1000))])
            out = json.loads(buf.getvalue())
            self.assertEqual(sorted((e["calendar"], e["autoJoinPending"]) for e in out["events"]),
                             [("Off", False), ("On", True)])
            self.assertEqual([(f["name"], f["pendingAutoJoin"]) for f in out["feeds"]], [("Off", False), ("On", True)])

    def test_google_calendar_with_pending_auto_join_off(self):
        start = {"dateTime": "2026-11-16T10:00:00+09:00"}
        end = {"dateTime": "2026-11-16T10:30:00+09:00"}
        me_ = {"email": "me@example.com", "self": True, "responseStatus": "needsAction"}
        snap = {"calendars": [{"id": "me@example.com", "summary": "Me"}, {"id": "team", "summary": "Team"}],
                "events": {"me@example.com": [{"id": "1", "summary": "Mine", "start": start, "end": end, "attendees": [me_]}],
                           "team": [{"id": "2", "summary": "Team sync", "start": start, "end": end, "attendees": [me_]}]}}
        real_load = me.google.load
        me.google.load = lambda *a, **k: (snap, None)
        try:
            with tempfile.TemporaryDirectory() as d:
                cfg = os.path.join(d, "config.json")
                with open(cfg, "w") as fh:
                    json.dump({"calendars": [{"type": "google", "account": "default",
                                              "pendingAutoJoin": {"team": False}}]}, fh)
                import contextlib
                import io
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    me.main(["--config", cfg, "--now", str(int(dt.datetime(2026, 11, 16, 8, tzinfo=TOKYO).timestamp() * 1000))])
                out = json.loads(buf.getvalue())
        finally:
            me.google.load = real_load
        self.assertEqual({e["title"]: (e["calendarId"], e["participation"], e["autoJoinPending"]) for e in out["events"]},
                         {"Mine": ("me@example.com", "pending", True), "Team sync": ("team", "pending", False)})
        self.assertEqual(out["accounts"][0]["pendingAutoJoin"], {"team": False})

    def test_missing_config_is_unconfigured(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            me.main(["--config", "/nonexistent/kaigi.json"])
        self.assertFalse(json.loads(buf.getvalue())["configured"])

    def test_http_feed_rejected(self):
        text, err = me.fetch("http://example.invalid/x.ics", 300, True)
        self.assertIsNone(text)
        self.assertIn("https", err)


if __name__ == "__main__":
    unittest.main()


class SchemeHandlerTests(unittest.TestCase):
    def test_desktop_files_and_mimeapps(self):
        with tempfile.TemporaryDirectory() as tmp:
            apps = os.path.join(tmp, "data", "applications")
            os.makedirs(apps)
            with open(os.path.join(apps, "zoom.desktop"), "w") as fh:
                fh.write("[Desktop Entry]\nName=Zoom\nMimeType=application/x-zoom;x-scheme-handler/zoommtg;\n")
            conf = os.path.join(tmp, "config")
            os.makedirs(conf)
            with open(os.path.join(conf, "mimeapps.list"), "w") as fh:
                fh.write("[Default Applications]\nx-scheme-handler/msteams=teams-for-linux.desktop\n")
            env = {"XDG_DATA_HOME": os.path.join(tmp, "data"), "XDG_DATA_DIRS": os.path.join(tmp, "none"),
                   "XDG_CONFIG_HOME": conf, "XDG_CONFIG_DIRS": os.path.join(tmp, "none")}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                found = me.scheme_handlers()
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertTrue(found["zoommtg"])
        self.assertTrue(found["msteams"])
        self.assertFalse(found["slack"])


class WebBrowserTests(unittest.TestCase):
    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def test_lists_https_handlers_from_the_main_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home", "applications")
            system = os.path.join(tmp, "sys", "applications")
            https = "MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n"
            self.write(os.path.join(system, "google-chrome.desktop"),
                       "[Desktop Entry]\nType=Application\nName=Google Chrome\nExec=sh %U\n" + https +
                       "[Desktop Action new-private]\nName=Incognito\nExec=sh --incognito\n")
            self.write(os.path.join(system, "fox.desktop"),
                       "[Desktop Entry]\nType=Application\nName=Fox\nExec=sh --new-window %u --class \"Fox %%\" %i\n" + https)
            # Hidden by the user's own copy, a wrapper, and apps that are not browsers.
            self.write(os.path.join(system, "gone.desktop"), "[Desktop Entry]\nType=Application\nName=Gone\nExec=sh %u\n" + https)
            self.write(os.path.join(home, "gone.desktop"), "[Desktop Entry]\nHidden=true\n")
            self.write(os.path.join(system, "wrapper.desktop"), "[Desktop Entry]\nType=Application\nName=W\nNoDisplay=true\nExec=sh %u\n" + https)
            self.write(os.path.join(system, "zoom.desktop"), "[Desktop Entry]\nType=Application\nName=Zoom\nExec=sh %u\nMimeType=x-scheme-handler/zoommtg;\n")
            self.write(os.path.join(system, "missing.desktop"), "[Desktop Entry]\nType=Application\nName=Missing\nExec=no-such-binary-kaigi %u\n" + https)
            self.write(os.path.join(system, "wrapped.desktop"),
                       "[Desktop Entry]\nType=Application\nName=Wrapped\nExec=sh -c \"browser %u\"\n" + https)
            self.write(os.path.join(system, "-bad.desktop"), "[Desktop Entry]\nType=Application\nName=Bad\nExec=sh %u\n" + https)
            self.write(os.path.join(system, "vendor", "nested.desktop"), "[Desktop Entry]\nType=Application\nName=Nested\nExec=sh\n" + https)
            old = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "XDG_DATA_DIRS")}
            os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "home")
            os.environ["XDG_DATA_DIRS"] = os.path.join(tmp, "sys")
            try:
                found = me.web_browsers("google-chrome")
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        by_id = {b["id"]: b for b in found}
        self.assertEqual(sorted(by_id), ["fox.desktop", "google-chrome.desktop", "vendor-nested.desktop"])
        self.assertEqual(by_id["google-chrome.desktop"]["name"], "Google Chrome")
        self.assertEqual(by_id["google-chrome.desktop"]["exec"], ["sh", ""])
        self.assertEqual(by_id["fox.desktop"]["exec"], ["sh", "--new-window", "", "--class", "Fox %"])
        self.assertEqual(by_id["fox.desktop"]["urlAt"], 2)
        # Without a URL field code the URL goes last.
        self.assertEqual(by_id["vendor-nested.desktop"]["exec"], ["sh", ""])
        # "sh" is no Chrome, so no profile flag for any of them.
        self.assertFalse(any(b["profiles"] for b in found))

    def test_chrome_family_follows_the_profiles_that_were_read(self):
        self.assertEqual(me.chrome_family(["/usr/bin/google-chrome-stable", ""]), "google-chrome")
        self.assertEqual(me.chrome_family(["chromium", ""]), "chromium")
        self.assertEqual(me.chrome_family(["firefox", ""]), "")
        # Beta keeps its profiles in ~/.config/google-chrome-beta.
        self.assertEqual(me.chrome_family(["/usr/bin/google-chrome-beta", ""]), "")
