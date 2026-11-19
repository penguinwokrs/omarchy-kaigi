// Pure selection, formatting and scheduling logic for Kaigi.
//
// Ported from MeetingBar (https://github.com/leits/MeetingBar, Apache-2.0):
//   Calendar/EventSelection.swift            -> nextEvent()
//   UI/StatusBar/StatusBarPresentation.swift -> titleMode(), timeLeftParts(), shortenTitle()
//   Notifications/NotificationPlanner.swift  -> dueActions()
//
// Qt-free so it runs under node (tests/model.test.js). Events are the objects
// bin/kaigi-events prints; times are epoch milliseconds.

var MINUTE = 60 * 1000

// MeetingBar's defaults, with config.json keys named after its Defaults keys.
var DEFAULT_CONFIG = {
  showEventsForPeriod: "today",               // today | today_tomorrow
  ongoingEventVisibility: "showTenMinBeforeNext", // hideImmediateAfter | showTenMinAfter | showTenMinBeforeNext
  personalEventsAppereance: "show_active",    // show_active | show_inactive | hide
  allDayEvents: "show",                       // show | show_with_meeting_link_only | hide
  nonAllDayEvents: "show",                    // show | show_inactive_without_meeting_link | hide_without_meeting_link
  showPendingEvents: "show",                  // show | show_inactive | hide
  showTentativeEvents: "show",                // show | show_inactive | hide
  declinedEventsAppereance: "strikethrough",  // strikethrough | hide
  pastEventsAppereance: "show_inactive",      // show_inactive | hide
  joinEventNotification: true,
  joinEventNotificationTime: 0,               // seconds before start
  endOfEventNotification: true,
  endOfEventNotificationTime: 0,              // seconds before end
  automaticEventJoin: false,
  automaticEventJoinTime: 0,                  // seconds before start
  actionGraceSeconds: 300,                    // still fire this late (suspend, shell restart)
  openMeetingsIn: "browser",                  // browser (MeetingBar's default) | webapp
  providerOpeningModes: {},                   // { zoom: "zoomApp", teams: "teamsApp", ... }
  refreshMinutes: 5,
  dismissedEvents: [],
  eventHooks: false,                          // run omarchy-hook kaigi-event-start / kaigi-event-end
  createMeetingService: "meet",               // meet | zoom | teams | jitsi
  bookmarks: []                               // ["Name https://…", …]
}

function withDefaults(config) {
  var out = {}
  var key
  for (key in DEFAULT_CONFIG) out[key] = DEFAULT_CONFIG[key]
  if (config && typeof config === "object")
    for (key in config) if (config[key] !== undefined && config[key] !== null) out[key] = config[key]
  return out
}

function startOfDay(ms) {
  var d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

function addDays(dayStartMs, days) {
  var d = new Date(dayStartMs)
  d.setDate(d.getDate() + days)
  return d.getTime()
}

function hasLink(event) {
  return !!(event && event.link && event.link.url)
}

function isDismissed(event, config) {
  var list = config.dismissedEvents || []
  for (var i = 0; i < list.length; i++) if (list[i] === event.id) return true
  return false
}

// EventSelection.nextEvent. Picks the event the bar title talks about.
function nextEvent(events, config, now, linkRequired) {
  config = withDefaults(config)
  var startPeriod = now + MINUTE
  var today = startOfDay(now)
  var endPeriod = addDays(today, config.showEventsForPeriod === "today_tomorrow" ? 2 : 1)
  var requiresLink = config.nonAllDayEvents === "hide_without_meeting_link"
  var visibility = config.ongoingEventVisibility

  var future = []
  for (var i = 0; i < (events || []).length; i++) {
    var e = events[i]
    if (e.end > startPeriod && e.start < endPeriod) future.push({ e: e, i: i })
  }
  future.sort(function(a, b) { return a.e.start === b.e.start ? a.i - b.i : a.e.start - b.e.start })

  var result = null
  for (var j = 0; j < future.length; j++) {
    var ev = future[j].e
    if (config.personalEventsAppereance === "hide" && !ev.hasAttendees) continue
    if (isDismissed(ev, config)) continue
    if (ev.allDay) continue
    if (!hasLink(ev) && (linkRequired || requiresLink)) continue
    if (ev.participation === "declined") continue
    if (ev.participation === "pending" && config.showPendingEvents === "hide") continue
    if (ev.participation === "tentative" && config.showTentativeEvents === "hide") continue
    if (ev.status === "cancelled") continue
    if (ev.start < now && visibility === "hideImmediateAfter") continue
    if (now >= ev.start + 10 * MINUTE && visibility === "showTenMinAfter") continue

    if (!result) { result = ev; continue }
    // An ongoing meeting hands over to the next one only when that one
    // begins within ten minutes; a future pick is never replaced.
    if (visibility === "showTenMinBeforeNext" && result.start <= now && ev.start < now + 10 * MINUTE) result = ev
    else break
  }
  return result
}

// StatusBarPresentationPolicy.mode
function titleMode(event, display, now) {
  if (!event) return "noUpcoming"
  if (!display || !display.showEventMaxTimeUntilEventEnabled) return "nextEvent"
  var threshold = Number(display.showEventMaxTimeUntilEventThreshold || 60) * MINUTE
  return event.start - now < threshold ? "nextEvent" : "afterThreshold"
}

function isOngoing(event, now) {
  return event.start <= now && event.end > now
}

// DateComponentsFormatter(.abbreviated, [.day, .hour, .minute]) between
// now - 60 s and the target, as StatusBarTitlePolicy.text does.
function timeLeftParts(event, now) {
  var target = isOngoing(event, now) ? event.end : event.start
  var minutes = Math.max(0, Math.floor((target - (now - MINUTE)) / MINUTE))
  return {
    ongoing: isOngoing(event, now),
    days: Math.floor(minutes / 1440),
    hours: Math.floor((minutes % 1440) / 60),
    minutes: minutes % 60
  }
}

// units: { day: "%1d", hour: "%1h", minute: "%1m", separator: " " }
function formatDuration(parts, units) {
  var out = []
  function put(n, fmt) { out.push(String(fmt).replace("%1", String(n))) }
  if (parts.days) put(parts.days, units.day)
  if (parts.hours) put(parts.hours, units.hour)
  if (parts.minutes || out.length === 0) put(parts.minutes, units.minute)
  return out.join(units.separator === undefined ? " " : units.separator)
}

function shortenTitle(rawTitle, limit, noTitle) {
  var title = String(rawTitle || noTitle || "").replace(/\s+/g, " ").trim()
  if (!title) title = String(noTitle || "")
  if (limit <= 0) return "..."
  var chars = Array.from(title)
  if (chars.length > limit) title = chars.slice(0, limit).join("").trim() + "..."
  return title
}

// --- menu ------------------------------------------------------------------

// How MeetingBar's menu shows one event, or null when it is hidden.
function menuAppearance(event, config, now) {
  config = withDefaults(config)
  if (isDismissed(event, config) || event.status === "cancelled") return null
  var past = event.end <= now
  var personal = !event.hasAttendees
  var inactive = false
  if (event.allDay) {
    if (config.allDayEvents === "hide") return null
    if (config.allDayEvents === "show_with_meeting_link_only" && !hasLink(event)) return null
  } else if (!hasLink(event)) {
    if (config.nonAllDayEvents === "hide_without_meeting_link") return null
    if (config.nonAllDayEvents === "show_inactive_without_meeting_link") inactive = true
  }
  if (personal) {
    if (config.personalEventsAppereance === "hide") return null
    if (config.personalEventsAppereance === "show_inactive") inactive = true
  }
  if (event.participation === "declined" && config.declinedEventsAppereance === "hide") return null
  if (event.participation === "pending") {
    if (config.showPendingEvents === "hide") return null
    if (config.showPendingEvents === "show_inactive") inactive = true
  }
  if (event.participation === "tentative") {
    if (config.showTentativeEvents === "hide") return null
    if (config.showTentativeEvents === "show_inactive") inactive = true
  }
  if (past) {
    if (config.pastEventsAppereance === "hide") return null
    inactive = true
  }
  return {
    inactive: inactive,
    past: past,
    ongoing: isOngoing(event, now),
    declined: event.participation === "declined",
    pending: event.participation === "pending",
    joinable: hasLink(event)
  }
}

// [{ key: "today"|"tomorrow", dayStart, rows: [{ event, look }] }]
function menuSections(events, config, now) {
  config = withDefaults(config)
  var today = startOfDay(now)
  var days = config.showEventsForPeriod === "today_tomorrow" ? 2 : 1
  var sections = []
  for (var d = 0; d < days; d++) {
    var from = addDays(today, d)
    var to = addDays(today, d + 1)
    var rows = []
    for (var i = 0; i < (events || []).length; i++) {
      var e = events[i]
      // All-day events belong to the days they cover; timed ones to the day
      // they start (or today, when they started earlier and still run).
      var belongs = e.allDay ? (e.start < to && e.end > from)
        : (e.start >= from && e.start < to) || (d === 0 && e.start < from && e.end > now)
      if (!belongs) continue
      var look = menuAppearance(e, config, now)
      if (look) rows.push({ event: e, look: look })
    }
    rows.sort(function(a, b) {
      if (a.event.allDay !== b.event.allDay) return a.event.allDay ? -1 : 1
      return a.event.start - b.event.start
    })
    sections.push({ key: d === 0 ? "today" : "tomorrow", dayStart: from, rows: rows })
  }
  return sections
}

// --- actions ---------------------------------------------------------------

// EventFiltering.filter: the list MeetingBar keeps after its display filters
// (title regexes are applied by bin/kaigi-events). Notifications and auto-join
// are planned from this list only, so "hide" settings also stop them, while
// show_inactive / show_underlined do not.
function passesEventFilter(event, config) {
  config = withDefaults(config)
  if (event.allDay) {
    if (config.allDayEvents === "hide") return false
    if (config.allDayEvents === "show_with_meeting_link_only" && !hasLink(event)) return false
  } else if (config.nonAllDayEvents === "hide_without_meeting_link" && !hasLink(event)) {
    return false
  }
  if (event.participation === "pending" && config.showPendingEvents === "hide") return false
  if (event.participation === "tentative" && config.showTentativeEvents === "hide") return false
  if (event.participation === "declined" && config.declinedEventsAppereance === "hide") return false
  return true
}

// Rows for the "auto-join unanswered invitations" switches: one per Google
// calendar shown (accounts from kaigi-events) and one per iCal feed.
// calendarId is "" for a feed. Unset means on.
function pendingAutoJoinRows(accounts, feeds) {
  var rows = []
  accounts = accounts || []
  for (var a = 0; a < accounts.length; a++) {
    var acct = accounts[a] || {}
    var chosen = acct.calendarIds && acct.calendarIds.length ? acct.calendarIds : (acct.activeIds || [])
    var map = acct.pendingAutoJoin && typeof acct.pendingAutoJoin === "object" ? acct.pendingAutoJoin : {}
    var cals = acct.calendars || []
    for (var c = 0; c < cals.length; c++) {
      var cal = cals[c] || {}
      var id = String(cal.id || "")
      if (!id || (chosen.indexOf(id) === -1 && !(cal.primary && chosen.indexOf("primary") !== -1))) continue
      rows.push({
        key: String(acct.account || "") + ":" + id,
        index: acct.configIndex,
        calendarId: id,
        name: String(cal.summary || id),
        owner: accounts.length > 1 ? String(acct.email || acct.account || "") : "",
        on: map[id] !== false
      })
    }
  }
  feeds = feeds || []
  for (var f = 0; f < feeds.length; f++) {
    var feed = feeds[f] || {}
    rows.push({ key: "feed:" + feed.configIndex, index: feed.configIndex, calendarId: "",
                name: String(feed.name || ""), owner: "", on: feed.pendingAutoJoin !== false })
  }
  return rows
}

// ---- snooze -----------------------------------------------------------------
//
// "Remind me again" on a start notification stores snooze:<event id> = due
// time in fired.json (pruneFired keeps future times), so it survives a shell
// restart. dueSnoozes returns the ones due now; a snooze whose meeting has
// ended, or that is no longer listed, is dropped.

var SNOOZE_PREFIX = "snooze:"

function snoozeKey(eventId) { return SNOOZE_PREFIX + String(eventId) }

function dueSnoozes(events, fired, now) {
  var due = [], stale = []
  for (var key in fired || {}) {
    if (key.indexOf(SNOOZE_PREFIX) !== 0) continue
    var id = key.slice(SNOOZE_PREFIX.length)
    var event = null
    for (var i = 0; i < (events || []).length; i++) if (events[i].id === id) { event = events[i]; break }
    if (!event || now >= event.end) { stale.push(key); continue }
    if (now >= Number(fired[key])) due.push({ key: key, event: event })
  }
  return { due: due, stale: stale }
}

// ---- dismiss ----------------------------------------------------------------
//
// dismissedEvents holds event ids hidden from the menu, notifications and
// auto-join. Ids of events no longer listed are dropped as new ones are added.
function withDismissed(list, eventId, events) {
  var listed = {}
  for (var i = 0; i < (events || []).length; i++) listed[events[i].id] = true
  var out = (list || []).filter(function(id) { return listed[id] && id !== eventId })
  out.push(String(eventId))
  return out.slice(-200)
}

// ---- event details ------------------------------------------------------------
//
// One line for the popup: "Attendees (12): Ana, Ben, … +4". label carries %1
// for the count, more carries %1 for the names left out. The organizer comes
// first; your own entry is left out.
function attendeeSummary(event, label, more, max) {
  var list = (event && event.attendees) || []
  var count = Math.max(Number(event && event.attendeeCount) || 0, list.length)
  if (count === 0) return ""
  var people = list.filter(function(a) { return a && !a.self })
  people.sort(function(a, b) { return (b.organizer ? 1 : 0) - (a.organizer ? 1 : 0) })
  var shown = people.slice(0, max).map(function(a) { return String(a.name) })
  var rest = count - shown.length - (list.some(function(a) { return a && a.self }) ? 1 : 0)
  var text = String(label).replace("%1", String(count)) + " " + shown.join(", ")
  if (rest > 0) text += (shown.length ? ", " : "") + String(more).replace("%1", String(rest))
  return text
}

// ---- new meetings and bookmarks ---------------------------------------------

var CREATE_MEETING = [
  { service: "meet", name: "Google Meet", url: "https://meet.new" },
  { service: "zoom", name: "Zoom", url: "https://zoom.us/start/videomeeting" },
  { service: "teams", name: "Microsoft Teams", url: "https://teams.microsoft.com/l/meeting/new" },
  { service: "jitsi", name: "Jitsi Meet", url: "https://meet.jit.si/" }
]

function createMeetingEntry(service) {
  for (var i = 0; i < CREATE_MEETING.length; i++) if (CREATE_MEETING[i].service === service) return CREATE_MEETING[i]
  return CREATE_MEETING[0]
}

// random: a function returning [0, 1), for Jitsi's room name.
// email: for Meet, the Google account to create it as (authuser, the way
// joining adds it). meet.new always redirects to authuser=0, and with a
// query it redirects to www.google.com, so this uses meet.google.com/new,
// MeetingBar's URL.
function createMeetingUrl(service, random, email) {
  var entry = createMeetingEntry(service)
  if (entry.service === "meet" && email) return "https://meet.google.com/new?authuser=" + encodeURIComponent(email)
  if (entry.service !== "jitsi") return entry.url
  var letters = "abcdefghijkmnpqrstuvwxyz23456789", room = "Kaigi-"
  for (var j = 0; j < 12; j++) room += letters.charAt(Math.floor((random || Math.random)() * letters.length))
  return entry.url + room
}

// The signed-in Google accounts a new Meet meeting can be created as, from
// kaigi-events' accounts list (one entry per Google calendar; several can
// share an account): [{ email, profile }], one per address, in config order.
// profile is the account's Chrome profile (per calendar, else the global
// one), which only applies when meetings open as web apps.
function createMeetingAccounts(accounts, config) {
  var out = [], seen = {}
  var fallback = String((config && config.chromeProfile) || "")
  for (var i = 0; i < (accounts || []).length && out.length < 10; i++) {
    var a = accounts[i]
    var email = a && typeof a.email === "string" ? a.email.trim() : ""
    if (!email || seen[email.toLowerCase()]) continue
    seen[email.toLowerCase()] = true
    out.push({ email: email, profile: String(a.chromeProfile || "") || fallback })
  }
  return out
}

// Bookmarks are lines "Name https://…" (the URL is the last word) or a bare
// URL; entries whose URL the launcher would refuse are skipped.
function parseBookmarks(list) {
  var out = []
  for (var i = 0; i < (list || []).length && out.length < 20; i++) {
    var line = typeof list[i] === "string" ? list[i].trim() : ""
    var m = /^(.*?)\s*(\S+)$/.exec(line)
    if (!m || !launchableUrl(m[2])) continue
    out.push({ name: m[1] || m[2].replace(/^[a-z.-]+:\/\//, "").slice(0, 60), url: m[2] })
  }
  return out
}

function actionIdentity(event, kind, offsetSeconds) {
  var anchor = kind === "eventEnd" ? event.end : event.start
  return event.id + "|" + Math.floor(anchor / 1000) + "|" + kind + "|" + offsetSeconds
}

// NotificationPlanner, evaluated on a tick instead of scheduled ahead: an
// action is due from its fire time until the grace window runs out, once.
// Returns [{ kind, event, identity }] sorted by fire time.
function dueActions(events, config, now, fired) {
  config = withDefaults(config)
  var grace = Math.max(0, Number(config.actionGraceSeconds) || 0) * 1000
  var out = []
  var plans = [
    { kind: "eventStart", enabled: !!config.joinEventNotification, offset: Number(config.joinEventNotificationTime) || 0, anchor: "start" },
    { kind: "eventEnd", enabled: !!config.endOfEventNotification, offset: Number(config.endOfEventNotificationTime) || 0, anchor: "end" },
    { kind: "autoJoin", enabled: !!config.automaticEventJoin, offset: Number(config.automaticEventJoinTime) || 0, anchor: "start", needsLink: true },
    { kind: "hookStart", enabled: config.eventHooks === true, offset: 0, anchor: "start" },
    { kind: "hookEnd", enabled: config.eventHooks === true, offset: 0, anchor: "end" }
  ]
  for (var i = 0; i < (events || []).length; i++) {
    var e = events[i]
    if (!passesEventFilter(e, config)) continue
    // NotificationPlanner.shouldConsider
    if (isDismissed(e, config) || e.status === "cancelled" || e.participation === "declined" || e.allDay) continue
    for (var p = 0; p < plans.length; p++) {
      var plan = plans[p]
      if (!plan.enabled) continue
      if (plan.needsLink && !hasLink(e)) continue
      // A calendar can opt out of auto-joining invitations not answered yet
      // (kaigi-events sets autoJoinPending from its pendingAutoJoin setting).
      if (plan.kind === "autoJoin" && e.participation === "pending" && e.autoJoinPending === false) continue
      var anchor = plan.anchor === "end" ? e.end : e.start
      var fireAt = anchor - plan.offset * 1000
      // Past the anchor (start or end) a start-type action is stale.
      var lastUseful = Math.min(fireAt + grace, plan.anchor === "end" ? e.end + grace : e.end)
      if (now < fireAt || now > lastUseful) continue
      var identity = actionIdentity(e, plan.kind, plan.offset)
      if (fired && fired[identity]) continue
      out.push({ kind: plan.kind, event: e, identity: identity, fireAt: fireAt })
    }
  }
  out.sort(function(a, b) { return a.fireAt - b.fireAt })
  return out
}

// Fired-identity bookkeeping kept on disk; drop entries older than two days.
function pruneFired(fired, now) {
  var out = {}
  for (var key in fired || {}) if (now - Number(fired[key]) < 2 * 24 * 60 * MINUTE) out[key] = fired[key]
  return out
}

// Schemes the launcher may hand to a browser or xdg-open.
function launchableUrl(url) {
  return /^(https?|zoommtg|discord|msteams|jitsi-meet|slack|riversidefm|riverside\.fm|tuple|workchat):\/\/[^\s"'<>]+$/.test(String(url || ""))
}

// --- opening a meeting -------------------------------------------------------
//
// Ported from MeetingBar's MeetingOpener.swift / MeetingProvider.swift: each
// service may open in its native app (MeetingOpeningMode) instead of the
// browser. config.providerOpeningModes maps a service id to "default"
// (follow openMeetingsIn), "browser", "webapp", or one of the app modes below.

var OPENING_MODES = {
  zoom: ["zoomApp", "zoomWebApp"],
  zoomgov: ["zoomApp", "zoomWebApp"],
  teams: ["teamsApp"],
  jitsi: ["jitsiApp"],
  slack: ["slackApp"],
  riverside: ["riversideApp"],
  tuple: ["tupleApp"],
  facebook_workspace: ["workplaceApp"]
}

var APP_NAMES = {
  zoomApp: "Zoom", teamsApp: "Microsoft Teams", jitsiApp: "Jitsi", slackApp: "Slack",
  riversideApp: "Riverside", tupleApp: "Tuple", workplaceApp: "Workplace"
}

// The scheme each app mode hands to xdg-open (bin/kaigi-events reports which
// ones have a handler installed).
var APP_SCHEMES = {
  zoomApp: ["zoommtg"], teamsApp: ["msteams"], jitsiApp: ["jitsi-meet"], slackApp: ["slack"],
  riversideApp: ["riversidefm", "riverside.fm"], tupleApp: ["tuple"], workplaceApp: ["workchat"]
}

function setScheme(url, scheme) {
  return String(url).replace(/^[A-Za-z][A-Za-z0-9+.-]*:/, scheme + ":")
}

function isZoomHost(host) {
  return /(^|\.)zoom(-x)?\.(us|com|com\.cn|de)$/.test(host) || /(^|\.)zoomgov\.com$/.test(host)
}

// zoomWebOpenDestination: https://host/j/123?pwd=x -> zoommtg://host/join?confno=123&pwd=x.
// Personal rooms (/my/) never go through the app.
function zoomAppUrl(url) {
  if (/^https?:\/\/[^\/]+\/my\//.test(url) || url.indexOf("/j/") === -1) return ""
  return setScheme(url.replace(/\?/g, "&").replace("/j/", "/join?confno="), "zoommtg")
}

// ZoomNativeOpenStrategy's fallback, the reverse of zoomAppUrl.
function zoomHttpsUrl(url) {
  return setScheme(String(url).replace("&", "?").replace("/join?confno=", "/j/"), "https")
}

// ZoomWebAppURLPolicy: https://host/j/123456?pwd=x -> https://app.zoom.us/wc/123456/start?pwd=x.
function zoomWebAppUrl(url) {
  var m = /^https?:\/\/([^\/?#]+)\/j\/(\d{6,})\/?(\?[^#]*)?(#.*)?$/.exec(url)
  if (!m || !isZoomHost(m[1].toLowerCase())) return ""
  return "https://app.zoom.us/wc/" + m[2] + "/start" + (m[3] || "")
}

// SlackHuddleOpenStrategy: https://app.slack.com/huddle/T123/C456 -> slack://join-huddle?team=T123&id=C456.
function slackAppUrl(url) {
  var m = /^https?:\/\/[^\/?#]+\/huddle\/([A-Za-z0-9._-]+)\/([A-Za-z0-9._-]+)/.exec(url)
  return m ? "slack://join-huddle?team=" + m[1] + "&id=" + m[2] : ""
}

// TupleNativeURLPolicy: https://tuple.app/c/abc?x -> tuple://c/abc?x.
function tupleAppUrl(url) {
  var m = /^https:\/\/tuple\.app\/c\/([^?#]+)(.*)$/i.exec(url)
  return m ? "tuple://c/" + m[1] + m[2] : ""
}

// WorkplaceNativeURLPolicy: workchat://room/?joinurl=<the https URL, encoded>.
function workplaceAppUrl(url) {
  var m = /^https?:\/\/([^\/?#]+)\/groupcall\/[^\/?#]+/.exec(url)
  if (!m) return ""
  var host = m[1].toLowerCase()
  if (host !== "workplace.com" && !/\.workplace\.com$/.test(host)) return ""
  var encoded = encodeURIComponent(url).replace(/[!'()*]/g, function(c) {
    return "%" + c.charCodeAt(0).toString(16).toUpperCase()
  })
  return "workchat://room/?joinurl=" + encoded
}

function appUrlsFor(mode, url) {
  switch (mode) {
  case "zoomApp": var z = zoomAppUrl(url); return z ? [z] : []
  case "teamsApp": return [setScheme(url, "msteams")]
  case "jitsiApp": return [setScheme(url, "jitsi-meet")]
  case "slackApp": var s = slackAppUrl(url); return s ? [s] : []
  case "riversideApp": return [setScheme(url, "riversidefm"), setScheme(url, "riverside.fm")]
  case "tupleApp": var t = tupleAppUrl(url); return t ? [t] : []
  case "workplaceApp": var w = workplaceAppUrl(url); return w ? [w] : []
  }
  return []
}

function providerMode(config, service) {
  var modes = config.providerOpeningModes
  var mode = modes && typeof modes === "object" ? modes[service] : undefined
  return typeof mode === "string" && mode ? mode : "default"
}

// How to open an event's link. handlers maps a URL scheme to whether an app
// is registered for it (missing = unknown, assume yes). Returns
// { url, via: "browser" | "webapp" | "app", unavailable } where unavailable
// names the app when its link fell back to the browser, or null.
function openPlan(link, config, handlers) {
  config = withDefaults(config)
  if (!link || !launchableUrl(link.url)) return null
  var url = String(link.url)
  var service = String(link.service || "")
  var mode = providerMode(config, service)
  var via = mode === "browser" ? "browser"
    : mode === "webapp" ? "webapp"
    : config.openMeetingsIn === "webapp" ? "webapp" : "browser"

  function hasHandler(scheme) { return !handlers || handlers[scheme] !== false }
  function viaApp(candidates, name, fallback) {
    for (var i = 0; i < candidates.length; i++) {
      var scheme = candidates[i].split(":")[0]
      if (launchableUrl(candidates[i]) && hasHandler(scheme)) return { url: candidates[i], via: "app", unavailable: "" }
    }
    return { url: fallback, via: via, unavailable: name }
  }

  // zoommtg:// links in the event itself (MeetingBar's zoom_native).
  if (/^zoommtg:/.test(url)) return viaApp([url], "Zoom", zoomHttpsUrl(url))
  // Other custom schemes (discord://) only an app can open.
  if (!/^https?:/.test(url)) return { url: url, via: "app", unavailable: "" }

  var allowed = OPENING_MODES[service] || []
  if (allowed.indexOf(mode) === -1) return { url: url, via: via, unavailable: "" }
  if (mode === "zoomWebApp") return { url: zoomWebAppUrl(url) || url, via: via, unavailable: "" }
  var candidates = appUrlsFor(mode, url)
  if (candidates.length === 0) return { url: url, via: via, unavailable: "" }
  return viaApp(candidates, APP_NAMES[mode], url)
}

// For the settings window: [{ service, name, modes: [mode...] }].
var OPENING_SERVICES = [
  { service: "meet", name: "Google Meet" },
  { service: "zoom", name: "Zoom" },
  { service: "zoomgov", name: "ZoomGov" },
  { service: "teams", name: "Microsoft Teams" },
  { service: "jitsi", name: "Jitsi" },
  { service: "slack", name: "Slack" },
  { service: "riverside", name: "Riverside" },
  { service: "tuple", name: "Tuple" },
  { service: "facebook_workspace", name: "Facebook Workspace" }
]

// Notification text goes through an Omarchy component whose text format the
// plugin does not control; keep markup-shaped input literal.
function plainNotificationText(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// ---- Google helper requests -------------------------------------------------
//
// Service.qml runs one bin/kaigi-google command at a time; these keep the
// requests made meanwhile. A request is the helper's argument list.

function isGoogleLogin(args) { return !!args && args[0] === "login" }

// Add a request. The same request twice (a double click) waits once, and a
// newer sign-in replaces one that has not started.
function googleEnqueue(queue, args) {
  var key = JSON.stringify(args)
  var out = []
  for (var i = 0; i < (queue || []).length; i++) {
    if (JSON.stringify(queue[i]) === key) return queue
    if (isGoogleLogin(args) && isGoogleLogin(queue[i])) continue
    out.push(queue[i])
  }
  out.push(args)
  return out
}

// Take the next request: { args, rest }, or null when nothing waits. A sign-in
// goes last: it waits for the browser, and a request left behind it would
// have to end it again.
function googleDequeue(queue) {
  if (!queue || !queue.length) return null
  var at = 0
  for (var i = 0; i < queue.length; i++) {
    if (!isGoogleLogin(queue[i])) { at = i; break }
  }
  return { args: queue[at], rest: queue.slice(0, at).concat(queue.slice(at + 1)) }
}

if (typeof module !== "undefined") {
  module.exports = {
    googleEnqueue: googleEnqueue,
    googleDequeue: googleDequeue,
    DEFAULT_CONFIG: DEFAULT_CONFIG,
    withDefaults: withDefaults,
    nextEvent: nextEvent,
    titleMode: titleMode,
    timeLeftParts: timeLeftParts,
    formatDuration: formatDuration,
    shortenTitle: shortenTitle,
    menuAppearance: menuAppearance,
    menuSections: menuSections,
    dueActions: dueActions,
    passesEventFilter: passesEventFilter,
    snoozeKey: snoozeKey,
    dueSnoozes: dueSnoozes,
    withDismissed: withDismissed,
    CREATE_MEETING: CREATE_MEETING,
    createMeetingUrl: createMeetingUrl,
    createMeetingAccounts: createMeetingAccounts,
    parseBookmarks: parseBookmarks,
    attendeeSummary: attendeeSummary,
    pendingAutoJoinRows: pendingAutoJoinRows,
    actionIdentity: actionIdentity,
    pruneFired: pruneFired,
    launchableUrl: launchableUrl,
    openPlan: openPlan,
    OPENING_MODES: OPENING_MODES,
    OPENING_SERVICES: OPENING_SERVICES,
    APP_NAMES: APP_NAMES,
    APP_SCHEMES: APP_SCHEMES,
    plainNotificationText: plainNotificationText,
    isOngoing: isOngoing
  }
}
