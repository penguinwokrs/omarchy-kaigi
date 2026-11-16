# Kaigi Privacy Policy

Kaigi is an open-source plugin for the Omarchy desktop. It runs entirely on
your own computer. It has no server, and the author operates no service that
receives your data.

## What Kaigi accesses

When you sign in with Google, Kaigi asks for one permission: **read-only
access to Google Calendar** (`https://www.googleapis.com/auth/calendar.readonly`).
It uses that permission to:

- list your calendars, so it knows which ones are shown (selected) in Google
  Calendar
- read events from now through tomorrow: title, time, location, description,
  conference link, and your own RSVP status

Kaigi never creates, changes, or deletes anything in your Google account.

## Where your data goes

- **Calendar data** goes directly from Google's API to your computer. Kaigi
  keeps a short-lived cache in `~/.cache/kaigi/`, readable only by your user,
  to show the next meeting in the bar.
- **The sign-in token** (OAuth refresh token) is stored in your desktop
  keyring (GNOME Keyring through the Secret Service API). Only if no keyring
  is available does it fall back to a file readable only by your user under
  `~/.local/state/kaigi/`.
- **Nothing is sent anywhere else.** Kaigi has no analytics, no telemetry,
  and no third-party services. The only network requests it makes go to
  Google's OAuth and Calendar endpoints. Opening a meeting link hands that
  link to your own browser.

## Removing your data

- **Sign out:** the "Sign out" button in Kaigi, or `bin/kaigi-google logout`,
  revokes the token with Google, deletes it from the keyring, and removes the
  cache.
- **Revoke access from Google's side:** you can also revoke Kaigi's access at
  any time at <https://myaccount.google.com/permissions>.
- **Uninstall:** deleting `~/.config/kaigi`, `~/.local/state/kaigi`, and
  `~/.cache/kaigi` removes everything Kaigi stored.

## Use of Google user data

Kaigi's use of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Contact

Open an issue at <https://github.com/penguinwokrs/omarchy-kaigi/issues>.
