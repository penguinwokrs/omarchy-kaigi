# Kaigi Privacy Policy

_Last updated: November 19, 2026_

Kaigi is an open-source plugin for the Omarchy desktop. It runs entirely on
your own computer. It has no server, and the author operates no service that
receives your data.

## Google user data Kaigi accesses

When you sign in with Google, Kaigi asks for two read-only permissions:

- **View events on all your calendars**
  (`https://www.googleapis.com/auth/calendar.events.readonly`)
- **See the list of Google calendars you're subscribed to**
  (`https://www.googleapis.com/auth/calendar.calendarlist.readonly`)

With them, Kaigi reads:

- **Your calendar list:** each calendar's ID, name, and color, and whether it
  is your primary calendar and whether it is shown (selected) in Google
  Calendar.
- **Your email address,** which is the ID of your primary calendar. Kaigi
  uses it to label the signed-in account.
- **Events on the calendars you show,** from the start of today through the
  end of tomorrow. Kaigi stores these events as the Google Calendar API
  returns them: title, start and end time, location, description, conference
  details, status, organizer, and attendees with their responses (including
  your own).

Kaigi never creates, changes, or deletes anything in your Google account.
It does not create aggregated or anonymized data from your Google data.

## How Kaigi uses that data

Kaigi uses Google user data only for features you see on your own desktop:

- show your next meeting and a countdown in the bar
- list today's (and optionally tomorrow's) meetings in the popup, dimming
  past meetings and striking through ones you declined
- find the meeting link (for example Google Meet or Zoom) and open it when
  you click it, or at the start time if you turn on auto-join
- show an event's location, description, and attendees when you open its
  details in the popup
- show desktop notifications on your computer when a meeting starts and ends
- if you turn on hooks, run your own scripts on your computer when a meeting
  starts and ends, passing them the event's title, start and end time, meeting
  link, and calendar name
- let you choose which calendars to show in the settings window
- open meeting links in the Chrome profile signed in to the same Google
  account, by matching your email address against the Google accounts
  signed in to each Chrome profile on your computer (Chrome's own "Local
  State" and "Preferences" files, which stay on your computer)
- open Google Meet links, including new meetings you start from the popup,
  as the right Google account, by adding your email address to the link
  (the `authuser` parameter). Kaigi adds it only to `https` links whose host
  is exactly `meet.google.com`, so your browser sends it only to Google

Kaigi does not use Google user data for advertising, profiling, analytics,
credit or lending decisions, or any purpose other than these features. Kaigi
does not use AI or machine-learning models, and it does not use Google user
data to develop, improve, or train any AI or machine-learning model.

## Sharing and transfer

**Kaigi does not share, transfer, or sell Google user data, raw or
aggregated/anonymized, to anyone.** That includes the author, advertisers,
data brokers, and AI services.

- Calendar data goes directly from Google's API to your computer and stays
  there. The author never receives it.
- Kaigi has no analytics, no telemetry, and no third-party services. Its only
  network requests related to your Google account go to Google's OAuth and
  Calendar API endpoints.
- When you open a meeting, Kaigi passes only that meeting's link to your
  browser or to the meeting app on your computer.
- Hooks are off by default. If you turn them on, Kaigi passes the details
  listed above to scripts you put in `~/.config/omarchy/hooks/` on your own
  computer. Kaigi itself sends nothing anywhere; what your scripts do is up
  to you.

## How the data is protected

- All requests to Google use HTTPS.
- Sign-in uses Google's OAuth 2.0 for installed apps with PKCE and a random
  `state` value. The sign-in response is received only on your own computer
  (`127.0.0.1`).
- **The sign-in token** (OAuth refresh token) is stored in your desktop
  keyring (GNOME Keyring through the Secret Service API). Only if no keyring
  is available does it fall back to a file under `~/.local/state/kaigi/` that
  only your user can read.
- Short-lived access tokens are kept in memory and never written to disk.
- Kaigi's cache (`~/.cache/kaigi/`) and state (`~/.local/state/kaigi/`) files
  are created so that only your user account can read them (mode 0600).
- Kaigi asks only for read-only permissions, and its source code is public
  so anyone can check what it does.

## Retention and deletion

- **Calendar cache:** the events and calendar list described above are kept
  in `~/.cache/kaigi/` so the bar can update without contacting Google every
  minute. The cache covers only today and tomorrow, and Kaigi replaces it on
  every refresh (every 5 minutes by default). It stays on your computer until
  you sign out or delete it.
- **Account details:** your email address and the refresh token are kept
  until you sign out.
- **Sign out:** the "Sign out" button in Kaigi, or `bin/kaigi-google logout`,
  revokes the token with Google, deletes it from the keyring, removes the
  account from Kaigi's settings, and deletes that account's calendar cache.
  If Google does not confirm the revocation and the token cannot be deleted
  from the keyring either, or the keyring cannot be reached to find the
  token, Kaigi changes nothing, keeps the account and shows
  an error so you can try again. If only the revocation is unconfirmed (for
  example, you are offline), Kaigi deletes the token and the account from
  your computer and asks you to remove its access at
  <https://myaccount.google.com/permissions>.
- **Revoke access from Google's side:** you can revoke Kaigi's access at any
  time at <https://myaccount.google.com/permissions>. Kaigi then can no longer
  read your calendar. To also remove data already cached on your computer,
  sign out in Kaigi or delete the folders below.
- **Uninstall:** first sign out of each Google account in Kaigi (settings
  window, Calendars tab), which revokes the token and deletes it from the
  keyring. Then run `omarchy plugin remove penguinwokrs.kaigi` and delete
  `~/.config/kaigi`, `~/.local/state/kaigi`, and `~/.cache/kaigi`. Deleting
  the folders alone leaves the token in the keyring: if you already did,
  remove it with `secret-tool clear service kaigi-google` and revoke Kaigi's
  access at <https://myaccount.google.com/permissions>.

Because the author never receives your data, there is nothing stored
elsewhere to delete.

## Use of Google user data

Kaigi's use and transfer of information received from Google APIs adheres to
the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Changes to this policy

Changes are published on this page, with the date at the top updated. The
history of every change is in the
[source repository](https://github.com/penguinwokrs/omarchy-kaigi/commits/main/PRIVACY.md).

## Contact

Open an issue at <https://github.com/penguinwokrs/omarchy-kaigi/issues>.
