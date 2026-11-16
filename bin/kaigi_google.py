"""Google Calendar API source for Kaigi (MeetingBar's "Google Calendar API" provider).

OAuth 2.0 for installed apps: loopback redirect on 127.0.0.1 with PKCE (S256)
and a random state. The OAuth client is the user's own "Desktop app" client
(~/.config/kaigi/google-client.json, 0600); MeetingBar's is compiled into its
release builds and cannot be reused. The refresh token is kept in the Secret
Service keyring (secret-tool) and, only when no keyring is reachable, in a
0600 file. Access tokens are never written anywhere.

Scope: calendar.readonly. API responses are cached for `refreshMinutes`
(0600, ~/.cache/kaigi) so the once-a-minute helper rarely touches the
network.
"""

import base64
import datetime as dt
import hashlib
import html
import http.server
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "kaigi")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")), "kaigi")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")), "kaigi")
CLIENT_PATH = os.path.join(CONFIG_DIR, "google-client.json")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
ACCOUNTS_PATH = os.path.join(STATE_DIR, "google-accounts.json")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CONSOLE_URL = "https://console.cloud.google.com/apis/credentials"

TIMEOUT = 15
MAX_RESPONSE = 10 * 1024 * 1024
MAX_PAGES = 10
SECRET_SERVICE = "kaigi-google"


class GoogleError(Exception):
    code = "google_error"


class ClientMissing(GoogleError):
    code = "client_missing"


class AuthRequired(GoogleError):
    code = "auth_required"


# --------------------------------------------------------------------------
# small file helpers


def write_private(path, text):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# --------------------------------------------------------------------------
# HTTP (injectable for tests)


class Http:
    def request(self, method, url, data=None, headers=None):
        body = None
        headers = dict(headers or {})
        headers.setdefault("User-Agent", "omarchy-kaigi")
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read(MAX_RESPONSE + 1)
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(MAX_RESPONSE + 1)
            status = exc.code
        if len(raw) > MAX_RESPONSE:
            raise GoogleError("response too large")
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            payload = {}
        return status, payload


# --------------------------------------------------------------------------
# OAuth client and secrets


def load_client(path=CLIENT_PATH):
    doc = read_json(path, None)
    if not isinstance(doc, dict):
        raise ClientMissing("Google OAuth client is not set up")
    inner = doc.get("installed") or doc.get("web") or doc
    cid, secret = inner.get("client_id"), inner.get("client_secret")
    if not cid or not str(cid).endswith(".apps.googleusercontent.com"):
        raise ClientMissing("google-client.json has no client_id")
    return {"client_id": str(cid), "client_secret": str(secret or "")}


def setup_client(source=None, dest=CLIENT_PATH, downloads=os.path.join(HOME, "Downloads")):
    """Copy a downloaded client_secret_*.json into place (0600). Returns the source used."""
    if not source:
        cands = []
        try:
            for name in os.listdir(downloads):
                # Cloud Console names it client_secret_<id>.json, or just
                # <id>.apps.googleusercontent.com(.json) on newer pages.
                if (name.startswith("client_secret") and name.endswith(".json")) or \
                        name.endswith((".apps.googleusercontent.com", ".apps.googleusercontent.com.json")):
                    p = os.path.join(downloads, name)
                    cands.append((os.path.getmtime(p), p))
        except OSError:
            pass
        if not cands:
            raise ClientMissing(f"no downloaded OAuth client JSON in {downloads}")
        source = max(cands)[1]
    load_client(source)  # validates
    with open(source, encoding="utf-8") as fh:
        write_private(dest, fh.read())
    return source


class Secrets:
    """Refresh tokens in the keyring, with a 0600 file fallback."""

    def __init__(self, state_dir=STATE_DIR, tool=None):
        self.state_dir = state_dir
        self.tool = tool if tool is not None else shutil.which("secret-tool")

    def _file(self, account):
        return os.path.join(self.state_dir, f"google-token-{hashlib.sha256(account.encode()).hexdigest()[:16]}")

    def store(self, account, token):
        if self.tool:
            try:
                r = subprocess.run([self.tool, "store", "--label", f"Kaigi Google ({account})",
                                    "service", SECRET_SERVICE, "account", account],
                                   input=token.encode(), capture_output=True, timeout=20)
                if r.returncode == 0:
                    try:
                        os.remove(self._file(account))
                    except OSError:
                        pass
                    return "keyring"
            except (OSError, subprocess.SubprocessError):
                pass
        write_private(self._file(account), token)
        return "file"

    def lookup(self, account):
        if self.tool:
            try:
                r = subprocess.run([self.tool, "lookup", "service", SECRET_SERVICE, "account", account],
                                   capture_output=True, timeout=20)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.decode().strip()
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            with open(self._file(account), encoding="utf-8") as fh:
                return fh.read().strip() or None
        except OSError:
            return None

    def clear(self, account):
        if self.tool:
            try:
                subprocess.run([self.tool, "clear", "service", SECRET_SERVICE, "account", account],
                               capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            os.remove(self._file(account))
        except OSError:
            pass


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def pkce_pair():
    verifier = b64url(secrets.token_bytes(48))
    return verifier, b64url(hashlib.sha256(verifier.encode()).digest())


# --------------------------------------------------------------------------
# Login (loopback + PKCE)

DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>Kaigi</title>
<body style="font-family:sans-serif;padding:3em;background:#111;color:#ddd">
<h2>{title}</h2><p>{body}</p></body>"""


def _callback_server():
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if "code" not in query and "error" not in query:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in query.items()})
            ok = "code" in query
            page = DONE_PAGE.format(
                title="Kaigi: ログインしました / Signed in" if ok else "Kaigi: ログインできませんでした",
                body="このタブは閉じて構いません。 You can close this tab." if ok
                else html.escape(query.get("error", ["error"])[0]))
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    return server, result


def default_opener(url):
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def login(account="default", http_client=None, opener=default_opener, secrets_store=None,
          client_path=CLIENT_PATH, accounts_path=ACCOUNTS_PATH, config_path=CONFIG_PATH,
          timeout=300, progress=lambda event: None):
    http_client = http_client or Http()
    secrets_store = secrets_store or Secrets()
    client = load_client(client_path)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    server, result = _callback_server()
    redirect = f"http://127.0.0.1:{server.server_address[1]}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state, "access_type": "offline", "prompt": "select_account consent",
    })
    progress({"event": "open", "url": url})
    opener(url)
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            server.timeout = max(0.1, min(1.0, deadline - time.time()))
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        raise GoogleError("timed out waiting for Google sign-in")
    if result.get("error"):
        raise GoogleError(f"sign-in was not completed ({result['error'][:60]})")
    if not secrets.compare_digest(result.get("state", ""), state):
        raise GoogleError("state mismatch; sign-in aborted")
    status, tok = http_client.request("POST", TOKEN_URL, {
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "code": result["code"], "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": redirect,
    })
    if status != 200 or not tok.get("refresh_token"):
        raise GoogleError(f"token exchange failed ({tok.get('error', status)})")
    status, primary = http_client.request("GET", f"{API}/users/me/calendarList/primary",
                                          headers={"Authorization": f"Bearer {tok['access_token']}"})
    email = str(primary.get("id") or "") if status == 200 else ""
    accounts = read_json(accounts_path, {})
    if account == "auto":
        # "Add account": key the account by its address, reusing the key of
        # an account already signed in with the same address.
        same = [k for k, v in accounts.items() if email and str(v.get("email", "")).lower() == email.lower()]
        account = same[0] if same else (email.lower() if email else "default")
    where = secrets_store.store(account, tok["refresh_token"])
    accounts[account] = {"email": email, "addedAt": int(time.time()), "storage": where}
    write_private(accounts_path, json.dumps(accounts, indent=2) + "\n")
    ensure_config_entry(account, config_path, email)
    progress({"event": "done", "account": account, "email": email, "storage": where})
    return email


def chrome_profile_for(email, config_home=None):
    """Chrome/Chromium profile folder whose signed-in Google account is `email`."""
    if not email:
        return ""
    config_home = config_home or os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config"))
    for browser in ("google-chrome", "chromium"):
        state = read_json(os.path.join(config_home, browser, "Local State"), {})
        cache = ((state.get("profile") or {}).get("info_cache") or {}) if isinstance(state, dict) else {}
        for folder, info in cache.items():
            if isinstance(info, dict) and str(info.get("user_name", "")).lower() == email.lower():
                return folder
    return ""


def ensure_config_entry(account, config_path=CONFIG_PATH, email="", config_home=None):
    config = read_json(config_path, {})
    if not isinstance(config, dict):
        config = {}
    cals = config.get("calendars")
    if not isinstance(cals, list):
        cals = []
    if not any(isinstance(c, dict) and c.get("type") == "google" and c.get("account", "default") == account for c in cals):
        entry = {"type": "google", "name": "Google", "account": account, "calendarIds": []}
        profile = chrome_profile_for(email, config_home)
        if profile:
            entry["chromeProfile"] = profile
        cals.append(entry)
        config["calendars"] = cals
        write_private(config_path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def logout(account="default", http_client=None, secrets_store=None, accounts_path=ACCOUNTS_PATH, config_path=CONFIG_PATH,
           cache_dir=CACHE_DIR):
    http_client = http_client or Http()
    secrets_store = secrets_store or Secrets()
    token = secrets_store.lookup(account)
    if token:
        try:
            http_client.request("POST", REVOKE_URL, {"token": token})
        except Exception:
            pass
    secrets_store.clear(account)
    accounts = read_json(accounts_path, {})
    accounts.pop(account, None)
    write_private(accounts_path, json.dumps(accounts, indent=2) + "\n")
    config = read_json(config_path, None)
    if isinstance(config, dict) and isinstance(config.get("calendars"), list):
        config["calendars"] = [c for c in config["calendars"]
                               if not (isinstance(c, dict) and c.get("type") == "google" and c.get("account", "default") == account)]
        write_private(config_path, json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    try:
        os.remove(os.path.join(cache_dir, cache_name(account)))
    except OSError:
        pass


def status(client_path=CLIENT_PATH, accounts_path=ACCOUNTS_PATH):
    try:
        load_client(client_path)
        client = True
    except ClientMissing:
        client = False
    accounts = read_json(accounts_path, {})
    return {"client": client, "accounts": [{"account": k, "email": v.get("email", "")} for k, v in accounts.items()],
            "consoleUrl": CONSOLE_URL}


# --------------------------------------------------------------------------
# API


def access_token(account, http_client, secrets_store, client_path=CLIENT_PATH):
    client = load_client(client_path)
    refresh = secrets_store.lookup(account)
    if not refresh:
        raise AuthRequired("Google sign-in required")
    status, tok = http_client.request("POST", TOKEN_URL, {
        "client_id": client["client_id"], "client_secret": client["client_secret"],
        "refresh_token": refresh, "grant_type": "refresh_token",
    })
    if status == 400 and tok.get("error") in ("invalid_grant", "unauthorized_client"):
        raise AuthRequired("Google sign-in expired; sign in again")
    if status != 200 or not tok.get("access_token"):
        raise GoogleError(f"token refresh failed ({tok.get('error', status)})")
    return tok["access_token"]


def api_get(http_client, token, path, params):
    status, payload = http_client.request("GET", f"{API}{path}?{urllib.parse.urlencode(params)}",
                                          headers={"Authorization": f"Bearer {token}"})
    if status == 401:
        raise AuthRequired("Google rejected the access token")
    if status != 200:
        msg = (payload.get("error") or {}).get("message", "") if isinstance(payload.get("error"), dict) else ""
        raise GoogleError(f"Calendar API HTTP {status} {msg[:80]}".strip())
    return payload


def rfc3339(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def download(account, cal_cfg, window_start, window_end, http_client, secrets_store, client_path=CLIENT_PATH):
    token = access_token(account, http_client, secrets_store, client_path)
    entries, page = [], None
    for _ in range(MAX_PAGES):
        params = {"maxResults": 250}
        if page:
            params["pageToken"] = page
        doc = api_get(http_client, token, "/users/me/calendarList", params)
        entries.extend(doc.get("items", []))
        page = doc.get("nextPageToken")
        if not page:
            break
    wanted = [str(x) for x in (cal_cfg.get("calendarIds") or [])]
    if wanted:
        chosen = [e for e in entries if e.get("id") in wanted or (e.get("primary") and "primary" in wanted)]
    else:
        chosen = [e for e in entries if e.get("selected") or e.get("primary")]
    out = {"fetchedAt": int(time.time()), "windowStart": rfc3339(window_start), "windowEnd": rfc3339(window_end),
           "calendars": [], "events": {}}
    for cal in chosen[:50]:
        cid = str(cal.get("id", ""))
        out["calendars"].append({"id": cid, "summary": str(cal.get("summaryOverride") or cal.get("summary") or cid)[:80],
                                 "color": str(cal.get("backgroundColor", ""))[:16], "primary": bool(cal.get("primary"))})
        items, page = [], None
        for _ in range(MAX_PAGES):
            params = {"timeMin": rfc3339(window_start), "timeMax": rfc3339(window_end), "singleEvents": "true",
                      "orderBy": "startTime", "maxResults": 250}
            if page:
                params["pageToken"] = page
            doc = api_get(http_client, token, f"/calendars/{urllib.parse.quote(cid, safe='')}/events", params)
            items.extend(doc.get("items", []))
            page = doc.get("nextPageToken")
            if not page:
                break
        out["events"][cid] = items[:1000]
    return out


def cache_name(account):
    return "google-" + hashlib.sha256(account.encode()).hexdigest()[:16] + ".json"


def load(account, cal_cfg, window_start, window_end, max_age, force,
         http_client=None, secrets_store=None, client_path=CLIENT_PATH, cache_dir=CACHE_DIR):
    """Returns (snapshot or None, error or None)."""
    http_client = http_client or Http()
    secrets_store = secrets_store or Secrets()
    path = os.path.join(cache_dir, cache_name(account))
    cached = read_json(path, None)
    covers = (isinstance(cached, dict) and cached.get("windowStart") == rfc3339(window_start)
              and cached.get("windowEnd") == rfc3339(window_end)
              and json.dumps(cached.get("calendarIds", [])) == json.dumps(cal_cfg.get("calendarIds") or []))
    if covers and not force and time.time() - cached.get("fetchedAt", 0) < max_age:
        return cached, None
    try:
        snap = download(account, cal_cfg, window_start, window_end, http_client, secrets_store, client_path)
        snap["calendarIds"] = cal_cfg.get("calendarIds") or []
        write_private(path, json.dumps(snap, ensure_ascii=False))
        return snap, None
    except GoogleError as exc:
        stale = cached if isinstance(cached, dict) else None
        return stale, exc
    except (OSError, ValueError) as exc:
        stale = cached if isinstance(cached, dict) else None
        return stale, GoogleError(f"network error ({type(exc).__name__})")


# --------------------------------------------------------------------------
# Event conversion (same shape as the iCalendar path)

RESPONSE = {"accepted": "accepted", "declined": "declined", "tentative": "tentative", "needsAction": "pending"}


def parse_time(obj, local):
    if not isinstance(obj, dict):
        raise ValueError("no time")
    if obj.get("dateTime"):
        return dt.datetime.fromisoformat(obj["dateTime"].replace("Z", "+00:00")), False
    if obj.get("date"):
        return dt.datetime.strptime(obj["date"], "%Y-%m-%d").replace(tzinfo=local), True
    raise ValueError("no time")


def conference_uri(item):
    data = item.get("conferenceData") or {}
    for ep in data.get("entryPoints") or []:
        if ep.get("entryPointType") == "video" and ep.get("uri"):
            return str(ep["uri"])
    return str(item.get("hangoutLink") or "")


def convert(snapshot, account_email, cal_name, helpers, custom, filters, local):
    """helpers: dict with find_link, add_authuser, strip_html, clip, to_ms, max_title, max_text."""
    clip, to_ms = helpers["clip"], helpers["to_ms"]
    out = []
    for cal in snapshot.get("calendars", []):
        for item in snapshot.get("events", {}).get(cal["id"], []):
            if not isinstance(item, dict) or item.get("eventType") == "workingLocation":
                continue
            try:
                start, all_day = parse_time(item.get("start"), local)
                end, _ = parse_time(item.get("end"), local)
            except ValueError:
                continue
            title = " ".join(str(item.get("summary") or "").split())
            if any(rx.search(title) for rx in filters):
                continue
            attendees = [a for a in item.get("attendees") or [] if isinstance(a, dict)]
            participation = "accepted"
            if attendees:
                me = next((a for a in attendees if a.get("self")), None)
                if me:
                    participation = RESPONSE.get(me.get("responseStatus"), "pending")
                elif not (item.get("organizer") or {}).get("self"):
                    participation = "unknown"
            description = str(item.get("description") or "")
            location = str(item.get("location") or "")
            fields = [("conference", conference_uri(item)), ("location", location), ("notes", description)]
            if "<" in description:
                fields.append(("htmlNotes", helpers["strip_html"](description)))
            link = helpers["find_link"](fields, custom)
            if link and account_email:
                link["url"] = helpers["add_authuser"](link["url"], account_email)
            status = str(item.get("status") or "confirmed")
            ident = f"{cal['id']}|{item.get('id', '')}"
            out.append({
                "id": hashlib.sha1(f"google|{ident}".encode()).hexdigest()[:16],
                "calendar": clip(cal_name if len(snapshot.get("calendars", [])) == 1 else cal["summary"], 80),
                "title": clip(title, helpers["max_title"]),
                "location": clip(location, helpers["max_text"]),
                "status": "cancelled" if status == "cancelled" else ("tentative" if status == "tentative" else "confirmed"),
                "participation": participation,
                "hasAttendees": bool(attendees),
                "link": link,
                "start": to_ms(start),
                "end": to_ms(end),
                "allDay": all_day,
                "lastModified": str(item.get("updated") or "")[:40],
                "color": cal.get("color", ""),
            })
    return out
