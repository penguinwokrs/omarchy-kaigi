# Kaigi for Omarchy

English | [日本語](README.ja.md)

> An unofficial port; not affiliated with or endorsed by MeetingBar.

A port of [MeetingBar](https://github.com/leits/MeetingBar) to the Omarchy shell.
It shows your next meeting and a countdown in the bar. Click it to see the day's
events and join with one click. It also sends notifications when a meeting starts
and ends, and can open the meeting by itself when it starts.

```
 Kaigi テスト定例 あと12分        ← bar (ongoing: "… 現在 (残り 25分)")
┌──────────────────────────────────────┐
│ 󰕧 次のミーティングに参加: Kaigi テスト定例 │
│ 今日  11月16日(月)                    │
│ ▍ 10:00 – 10:30  過去の打ち合わせ       │  (past: dimmed)
│ ▍ 12:31 – 13:01  Kaigi テスト定例   󰕧 │
│ ▍ 13:30 – 14:00  ~~辞退した会議~~      │  (declined: struck through)
│ 󰑐 更新   󰒓 設定                       │
└──────────────────────────────────────┘
```

## Install

Requires Omarchy 4.5 or later (it uses the Omarchy shell's plugin system).

```bash
omarchy plugin add https://github.com/penguinwokrs/omarchy-kaigi --enable
```

This installs Kaigi into `~/.config/omarchy/plugins/penguinwokrs.kaigi` and
puts the widget in `centerEnd`, next to the clock. Update it with
`omarchy plugin update penguinwokrs.kaigi`, and remove it with
`omarchy plugin remove penguinwokrs.kaigi`. Move the widget with
`omarchy bar move penguinwokrs.kaigi --section right`.

To work on the code, clone it anywhere and link it instead:

```bash
git clone https://github.com/penguinwokrs/omarchy-kaigi.git
cd omarchy-kaigi
./install.sh            # symlinks into ~/.config/omarchy/plugins and enables it
./install.sh --remove   # disables and unlinks it
```

Then open the popup and follow the Google sign-in steps below.

## Calendars: Google sign-in

Kaigi talks to the Google Calendar API, like MeetingBar's "Google Calendar
API" provider does, and ships its own OAuth client (`bin/google-client.json`),
as MeetingBar does. Open the popup, press **Googleでログイン / Sign in with
Google**, pick your account and allow read access. That's all.

> Kaigi's Google verification is in progress. Until it completes, Google shows
> a "Google hasn't verified this app" page during sign-in (choose *Advanced →
> Go to Kaigi*), and the shared client accepts at most 100 users. You can use
> your own client instead, as described below.

### Optional: use your own OAuth client (about 5 minutes)

It's free: the Calendar API costs nothing and needs no billing account, and
Kaigi uses a few hundred requests a day against a quota of 1,000,000. A client
you import takes precedence over the bundled one.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project, for example `kaigi`.
2. Open **APIs & Services → Library → Google Calendar API** and click
   **Enable**.
3. Open **APIs & Services → OAuth consent screen**:
   - **User type:** choose *External* for a personal Gmail account. For a
     Google Workspace account, *Internal* is enough if your admin allows it.
   - **App name and email:** anything you like.
   - **Scopes:** you don't need to add any; Kaigi asks for
     `calendar.events.readonly` and `calendar.calendarlist.readonly` when you
     sign in.
   - **Publishing status:** for *External*, click **Publish app → In
     production**. If you leave it in *Testing*, Google expires the sign-in
     after 7 days. You don't need verification for your own use, but sign-in
     shows a "Google hasn't verified this app" page. Click *Advanced → Go to …*
     to continue.
   - Publishing to production can require a homepage and a privacy policy
     link on the Branding page. This repository's URL and
     [PRIVACY.md](PRIVACY.md) work for that.
4. Open **Credentials → Create credentials → OAuth client ID** and choose the
   **Desktop app** type. Then click **Download JSON**.
5. In the Kaigi popup, press **ダウンロードしたJSONを取り込む / Import
   downloaded JSON**. This copies the newest downloaded client JSON
   (`client_secret_*.json` or `*.apps.googleusercontent.com.json`) from
   `~/Downloads` to `~/.config/kaigi/google-client.json` (0600). You can also run
   `bin/kaigi-google setup <file>`.
6. Press **Googleでログイン / Sign in with Google**, then approve access in the
   browser that opens.

When sign-in succeeds, Kaigi adds a Google entry to `config.json` and reads
the calendars that are checked (selected) in Google Calendar. Pick other
calendars on the settings window's Calendars tab.

You can add more accounts with **アカウントを追加 / Add account** in the popup
or the settings window. Each account is keyed by its address. If a Chrome
profile is signed in with that address, Kaigi uses it to open that account's
meetings.

### How it works

- **Sign-in:** OAuth for installed apps, with a loopback redirect on
  `127.0.0.1`, PKCE (S256) and a random `state`. Kaigi asks only to read events
  (`calendar.events.readonly`) and the calendar list
  (`calendar.calendarlist.readonly`).
- **Tokens:** the refresh token goes into the GNOME keyring through
  `secret-tool`. Only when no keyring is reachable does it fall back to a 0600
  file under `~/.local/state/kaigi/`. Access tokens are never written to
  disk.
- **Fetching:** Kaigi refetches events every `refreshMinutes` and caches them
  in `~/.cache/kaigi/` (0600). It uses `singleEvents=true`, so Google
  expands recurring events.
- **Links and RSVPs:** the meeting link comes from `conferenceData` or
  `hangoutLink` first, then the location and the description. Your RSVP comes
  from your own entry in `attendees` (`self: true`). Working-location entries
  are skipped.
- **Sign-out:** `ログアウト / Sign out` in the popup or the settings window,
  or `bin/kaigi-google logout --account <name>`, revokes the token, removes it from the keyring
  and deletes the cache.
- **Expired sign-in:** if Google rejects the sign-in (revoked, or 7 days in
  Testing), the popup shows a **再ログイン / Sign in again** button for that
  account only.

### Alternative: iCalendar feeds

You can still add calendars from `.ics` URLs or files to `"calendars"`, next
to the Google entry or instead of it:

```json
{ "name": "Work (ics)", "url": "https://…/basic.ics", "color": "#4285f4" }
{ "name": "Local", "path": "~/Calendars/team.ics" }
```

Only `https://` and `webcal://` URLs are fetched. For these feeds, `emails`
says which attendee is you.

## Settings

Open the settings window from the popup's **設定 / Settings** button, or run
`omarchy-shell kaigi openSettings`. Like MeetingBar's Preferences, it has
these tabs, and changes save immediately:

- **General:** auto-join, start and end notifications with their timing, and
  how and in which Chrome profile meetings open.
- **Calendars:** Google accounts (add or sign out), which calendars to show for
  each account, each account's Chrome profile, iCal feeds, and the display
  period.
- **Appearance:** the bar title, time left, title length, the ongoing-meeting
  rule, "only events starting soon", and the menu title length and end time.
- **Events:** all-day events, events without a meeting link, events without
  attendees, past events, and pending, tentative and declined events.
- **Advanced:** title filters, extra link patterns, refresh interval, grace
  period, and opening the config file.

Everything is stored in `~/.config/kaigi/config.json` (0600). From a script,
use `omarchy-shell kaigi set <key> <json>`, for example
`omarchy-shell kaigi set eventTimeFormat '"hide"'`.

Settings use MeetingBar's names and default values.

**Behaviour** goes in `config.json`:

| key | default | values |
|---|---|---|
| `showEventsForPeriod` | `today` | `today`, `today_tomorrow` |
| `ongoingEventVisibility` | `showTenMinBeforeNext` | `hideImmediateAfter`, `showTenMinAfter`, `showTenMinBeforeNext` |
| `personalEventsAppereance` | `show_active` | `show_active`, `show_inactive`, `hide` (events without attendees) |
| `allDayEvents` | `show` | `show`, `show_with_meeting_link_only`, `hide` |
| `nonAllDayEvents` | `show` | `show`, `show_inactive_without_meeting_link`, `hide_without_meeting_link` |
| `showPendingEvents` / `showTentativeEvents` | `show` | `show`, `show_inactive`, `hide` |
| `declinedEventsAppereance` | `strikethrough` | `strikethrough`, `hide` |
| `pastEventsAppereance` | `show_inactive` | `show_inactive`, `hide` |
| `joinEventNotification` / `…Time` | `true` / `0` | notification N seconds before start |
| `endOfEventNotification` / `…Time` | `true` / `0` | notification N seconds before end |
| `automaticEventJoin` / `…Time` | `false` / `0` | open the meeting N seconds before start. As in MeetingBar, this includes invitations you have not answered or answered "maybe"; set `showPendingEvents` / `showTentativeEvents` to `hide` to leave those out (which also hides them from the menu) |
| `actionGraceSeconds` | `300` | still fire this late, e.g. after suspend |
| `openMeetingsIn` | `browser` | `browser` opens the link with `xdg-open` in your default browser, like MeetingBar's "Default Browser". `webapp` opens it as its own window on the current workspace with `omarchy-launch-webapp` (Chromium-based browsers; an Omarchy addition) |
| `chromeProfile` | `""` | With `webapp`: the Chrome profile folder to open meetings in (`Default`, `Profile 2`, …; see `chrome://version`). Also settable per calendar. Empty means the last used profile. Useful if you keep Google accounts in separate Chrome profiles (an Omarchy addition; MeetingBar has no profiles) |
| `customRegexes` | `[]` | extra link patterns, tried last |
| `filterEventRegexes` | `[]` | hide events whose title matches |
| `dismissedEvents` | `[]` | event ids to ignore |

**Display** options also live in `config.json`. Values in the bar entry in
`shell.json` (`omarchy bar set penguinwokrs.kaigi <key> <value>`) are used
only when `config.json` doesn't set them:

| key | default | values |
|---|---|---|
| `eventTitleFormat` | `show` | `show`, `generic`, `dot`, `none` |
| `eventTimeFormat` | `show` | `show`, `hide` |
| `statusbarEventTitleLength` | `30` | 5–55 (MeetingBar uses 55; 30 fits better beside the clock) |
| `menuEventTitleLength` | `50` | |
| `showEventEndTime` | `true` | |
| `showEventMaxTimeUntilEventEnabled` / `…Threshold` | `false` / `60` | show only events starting within N minutes |

## Mouse, keys, IPC

- **Bar:** left-click opens the popup, middle-click joins the next meeting,
  right-click refetches the feeds.
- **Popup:** ↑/↓ (or k/j) to choose an event, Enter to join it, `n` to join
  the next meeting, `r` to refresh, Esc to close. Enter works only when an
  event is selected.
- **IPC:**
  - `omarchy-shell kaigi joinNext` (bind it to a key)
  - `omarchy-shell kaigi refresh`
  - `omarchy-shell kaigi next`
  - `omarchy-shell kaigi googleLogin`
  - `omarchy-shell kaigi openSettings`
  - `omarchy-shell kaigi set <key> <json>`
  - `omarchy-shell penguinwokrs.kaigi toggle`

## How it works

- `bin/kaigi_google.py` and `bin/kaigi-google` handle Google sign-in and
  the Calendar API, using only the Python standard library.
- `bin/kaigi-events` also uses only the standard library. It parses the
  feeds and expands recurrences (RRULE, EXDATE, RDATE, RECURRENCE-ID, TZID,
  DST), then finds the meeting link the way MeetingBar's link detector does.
  The 69 service patterns are in `bin/services.json`. It prints JSON.
- `Service.qml` runs once per shell. It polls the helper every minute and
  checks for due actions every 5 s. Before it notifies or joins, it records the
  action in `~/.local/state/kaigi/fired.json`. Because of that, multiple
  monitors, plugin reloads and `omarchy restart shell` never repeat an action.
- Only URLs that match a known service (or your `customRegexes`) with an
  `https`, `http`, `zoommtg` or `discord` scheme are opened. They are passed as
  argv, never through a shell.
- `Panel.qml` is the bar widget and popup, and `SettingsWindow.qml` is the
  settings window. `Model.js` holds the ported selection, formatting and
  scheduling logic.

## Development

Saving files under the plugin folder hot-reloads the bar widget. Changes to
`Service.qml` and `SettingsWindow.qml` take effect only after
`omarchy restart shell`.

## Tests

```bash
python3 -m unittest discover -s tests
TZ=Asia/Tokyo node --test tests/
```

## Not ported (yet)

These MeetingBar features are not in this version:

- macOS Calendar (EventKit): its Linux counterpart would be GNOME Online
  Accounts
- full-screen reminders
- snooze
- bookmarks
- AppleScript/Shortcuts hooks
- ad-hoc meeting creation
- per-service native apps or browsers
- the menu timeline
- event details submenu
- per-event dismiss from the menu

## Privacy

See [PRIVACY.md](PRIVACY.md). Kaigi reads your calendar read-only and sends nothing anywhere but Google's API.

## License

Apache-2.0. See `NOTICE` for the parts derived from MeetingBar.
