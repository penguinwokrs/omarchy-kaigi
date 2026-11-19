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
│ ▍ 15:00 – 15:30  採用面接  未返答   󰕧 │  (not answered: marked)
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

Kaigi talks to the Google Calendar API and ships its own OAuth client
(`bin/google-client.json`). Open the popup, press **Googleでログイン / Sign in with
Google**, pick your account and allow read access. That's all.

Google has verified Kaigi's OAuth client, so sign-in goes straight to Google's
permission screen with no "unverified app" warning.

- Kaigi asks only to **read** your events and calendar list. It never
  creates, changes, or deletes anything.
- Your data goes directly from Google to your computer and nowhere else
  ([privacy policy](PRIVACY.md)).

### Optional: use your own OAuth client (about 5 minutes)

You don't need this; the bundled client works for everyone. Use it only if
you'd rather sign in through a project in your own Google Cloud account.
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

The popup offers **Googleでログイン / Sign in with Google** until the first
account is signed in. Add more accounts with **アカウントを追加 / Add account**
on the settings window's Calendars tab. Each account is keyed by its address.
With `webapp`, each account's meetings open in the Chrome profile signed in
with that address: the profile whose Chrome sign-in it is, else one where it
is signed in to Google (the most recently used first). Kaigi looks this up
every time it reads your calendars, by address rather than by the account's
`authuser` number, so it keeps working when accounts sign in or out or move
between profiles. The Calendars tab shows which profile each account uses.

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
- **Sign-out:** `ログアウト / Sign out` on the settings window's Calendars tab,
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

### Auto-join for invitations you haven't answered

Auto-join also opens invitations you haven't answered yet. To stop that for
some calendars, turn them off under Settings → General → "Also auto-join
invitations you haven't answered, from". Each Google calendar and each iCal
feed has its own switch, and calendars you haven't set stay on. Turning one
off stops only the auto-join; you still get the start and end notifications.

In `config.json` this is `pendingAutoJoin` on the calendar entry:
`{"<calendar id>": false}` on a Google entry, or `false` on an iCal feed.

```json
{ "type": "google", "account": "me@example.com", "pendingAutoJoin": { "team@group.calendar.google.com": false } }
{ "name": "Local", "path": "~/Calendars/team.ics", "pendingAutoJoin": false }
```

## Settings

Open the settings window from the popup's **設定 / Settings** button, or run
`omarchy-shell kaigi openSettings`. It has these tabs, and changes save
immediately:

- **General:** auto-join (and, per calendar, whether it opens invitations you
  haven't answered), how and in which Chrome profile meetings open, the
  service for new meetings, bookmarks, and hooks.
- **Notifications:** start and end notifications with their timing.
- **Calendars:** Google accounts (add or sign out), which calendars to show for
  each account, each account's Chrome profile, iCal feeds, and the display
  period.
- **Appearance:** the bar title, time left, title length, the ongoing-meeting
  rule, "only events starting soon", and the menu title length and end time.
- **Events:** all-day events, events without a meeting link, events without
  attendees, past events, pending, tentative and declined events, and events
  you hid (show them again).
- **Advanced:** title filters, extra link patterns, refresh interval, grace
  period, and opening the config file.

Everything is stored in `~/.config/kaigi/config.json` (0600). From a script,
use `omarchy-shell kaigi set <key> <json>`, for example
`omarchy-shell kaigi set eventTimeFormat '"hide"'`.

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
| `automaticEventJoin` / `…Time` | `false` / `0` | open the meeting N seconds before start. This includes invitations you have not answered or answered "maybe". To leave out unanswered invitations from some calendars only, see [Auto-join for invitations you haven't answered](#auto-join-for-invitations-you-havent-answered). `showPendingEvents` / `showTentativeEvents` set to `hide` leave them out everywhere (and hide them from the menu) |
| `actionGraceSeconds` | `300` | still fire this late, e.g. after suspend |
| `openMeetingsIn` | `browser` | `browser` opens the link with `xdg-open` in your default browser. `webapp` opens it as its own window on the current workspace with `omarchy-launch-webapp` (Chromium-based browsers only) |
| `providerOpeningModes` | `{}` | per-service opening, e.g. `{"zoom": "zoomApp", "teams": "teamsApp"}`. Values: `default` (follow `openMeetingsIn`), `browser`, `webapp`, or an app mode from "Supported services" below. Without the app installed, the link opens in the browser |
| `chromeProfile` | `""` | With `webapp`: the Chrome profile folder to open meetings in (`Default`, `Profile 2`, …; see `chrome://version`). Empty means the last used profile. Google accounts use the profile signed in to them instead; this one is for iCal calendars and accounts no profile is signed in to. Also settable per calendar: on a Google calendar it is kept while that profile is still signed in to the account, otherwise Kaigi goes back to finding the profile |
| `customRegexes` | `[]` | extra link patterns, tried last |
| `filterEventRegexes` | `[]` | hide events whose title matches |
| `dismissedEvents` | `[]` | ids of events you hid with "Hide this event"; they get no notifications or auto-join either |
| `createMeetingService` | `meet` | service the popup's "New meeting" opens: `meet`, `zoom`, `teams`, `jitsi` |
| `bookmarks` | `[]` | meeting links you use often, listed in the popup: `["Daily https://meet.google.com/…", …]` (a name, then the URL) |
| `eventHooks` | `false` | run hooks when meetings start and end (see [Hooks](#hooks)) |

### Hooks

With `eventHooks` on, Kaigi runs `omarchy-hook kaigi-event-start` when a
meeting starts and `omarchy-hook kaigi-event-end` when it ends. Put
executable scripts at `~/.config/omarchy/hooks/kaigi-event-start` and
`~/.config/omarchy/hooks/kaigi-event-end` (or in `….d/` folders). They get
these arguments:

1. title
2. start time (ISO 8601, UTC)
3. end time (ISO 8601, UTC)
4. meeting link (empty if none)
5. calendar name

Hooks follow the same rules as notifications: declined, cancelled, all-day
and hidden events are skipped, and each one runs once.

**Display** options also live in `config.json`. Values in the bar entry in
`shell.json` (`omarchy bar set penguinwokrs.kaigi <key> <value>`) are used
only when `config.json` doesn't set them:

| key | default | values |
|---|---|---|
| `eventTitleFormat` | `show` | `show`, `generic`, `dot`, `none` |
| `eventTimeFormat` | `show` | `show`, `hide` |
| `statusbarEventTitleLength` | `30` | 5–55 (30 fits well beside the clock) |
| `menuEventTitleLength` | `50` | |
| `showEventEndTime` | `true` | |
| `showEventMaxTimeUntilEventEnabled` / `…Threshold` | `false` / `60` | show only events starting within N minutes |

## Supported services

Kaigi detects links of 69 services (patterns in `bin/services.json`): Google Meet, Zoom, Microsoft Teams, Webex,
Jitsi, Slack huddles, Discord, Whereby, Around, Lark / Feishu, StreamYard,
Riverside and more. It unwraps Outlook SafeLinks and Google redirects
first.

In Settings → General → "Per-service opening", these services can open in
their app. When the app is not installed (no handler for its URL scheme),
Kaigi shows a notification and opens the link in the browser.

| Service | Mode | Opens | Linux app |
|---|---|---|---|
| Zoom / ZoomGov | `zoomApp` | `zoommtg://…/join?confno=…` | Zoom's Linux client |
| Zoom / ZoomGov | `zoomWebApp` | `https://app.zoom.us/wc/<id>/start` (in the browser) | none needed |
| Microsoft Teams | `teamsApp` | `msteams://…` | e.g. teams-for-linux (there is no official Linux client) |
| Jitsi | `jitsiApp` | `jitsi-meet://…` | Jitsi Meet Electron |
| Slack | `slackApp` | `slack://join-huddle?team=…&id=…` | Slack's Linux client |
| Riverside | `riversideApp` | `riversidefm://…` | (no Linux client known) |
| Tuple | `tupleApp` | `tuple://c/…` | Tuple's app, if available for Linux |
| Facebook Workspace | `workplaceApp` | `workchat://room/?joinurl=…` | (no Linux client known) |

A `zoommtg://` link in the event opens in the Zoom app directly (or, without
it, as https in the browser), and `discord://` links open in Discord. Every
service can also be set to `browser` or `webapp` on its own.

## Mouse, keys, IPC

- **Bar:** left-click opens the popup, middle-click joins the next meeting,
  right-click refetches the feeds.
- **Popup:** click an event to join it. The ⌄ button at the right of an event
  (or a click on an event without a meeting link) shows its location,
  attendees and description, and a **Hide this event** button. **New meeting**
  opens a new meeting on the service set in Settings → General. For Google
  Meet with more than one Google account signed in, it first lists the
  accounts so you can pick which one to create the meeting as (Kaigi adds
  `authuser` to the Meet link, as it does when joining; with `webapp`, the
  account's Chrome profile is used too). **Bookmarks** lists your saved
  meeting links.
- **Popup keys:** ↑/↓ (or k/j) to choose an event, →/← to show or close its
  details, Enter to join it, `n` to join the next meeting, `r` to refresh, Esc
  to close. Enter works only when an event is selected.
- **Notifications:** the start notification has **Join** and **Remind me in 5
  min** buttons. The reminder has the same buttons, so you can put it off
  again.
- **IPC:**
  - `omarchy-shell kaigi joinNext` (bind it to a key)
  - `omarchy-shell kaigi refresh`
  - `omarchy-shell kaigi next`
  - `omarchy-shell kaigi googleLogin`
  - `omarchy-shell kaigi openSettings`
  - `omarchy-shell kaigi createMeeting <meet|zoom|teams|jitsi>` (`""` for the
    one set in Settings). For Meet with several accounts signed in it opens
    without choosing one, as before
  - `omarchy-shell kaigi createMeetingAs meet <email>` (a Meet meeting as
    that signed-in account)
  - `omarchy-shell kaigi set <key> <json>`
  - `omarchy-shell penguinwokrs.kaigi toggle`

## How it works

- `bin/kaigi_google.py` and `bin/kaigi-google` handle Google sign-in and
  the Calendar API, using only the Python standard library.
- `bin/kaigi-events` also uses only the standard library. It parses the
  feeds and expands recurrences (RRULE, EXDATE, RDATE, RECURRENCE-ID, TZID,
  DST), then finds the meeting link using the 69 service patterns in
  `bin/services.json`. It also checks which
  meeting-app URL schemes (`zoommtg`, …) have a handler. It prints JSON.
- `Service.qml` runs once per shell. It polls the helper every minute and
  checks for due actions every 5 s. Before it notifies or joins, it records the
  action in `~/.local/state/kaigi/fired.json`. Because of that, multiple
  monitors, plugin reloads and `omarchy restart shell` never repeat an action.
- Only URLs that match a known service (or your `customRegexes`) with an
  `https`, `http`, `zoommtg` or `discord` scheme, and the meeting-app URLs
  built from them (`msteams`, `jitsi-meet`, `slack`, `riversidefm`, `tuple`,
  `workchat`), are opened, as well as your bookmarks and new-meeting pages
  with the same schemes. They are passed as argv, never through a shell.
- `Panel.qml` is the bar widget and popup, and `SettingsWindow.qml` is the
  settings window. `Model.js` holds the event selection, formatting and
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

## Privacy

See [PRIVACY.md](PRIVACY.md). Kaigi reads your calendar read-only and sends nothing anywhere but Google's API.

## License

Apache-2.0. See `NOTICE` for the parts derived from MeetingBar.
