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
  openMeetingsIn: "webapp",                   // webapp | browser
  refreshMinutes: 5,
  dismissedEvents: []
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
    { kind: "autoJoin", enabled: !!config.automaticEventJoin, offset: Number(config.automaticEventJoinTime) || 0, anchor: "start", needsLink: true }
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
  return /^(https?|zoommtg|discord):\/\/[^\s"'<>]+$/.test(String(url || ""))
}

// Notification text goes through an Omarchy component whose text format the
// plugin does not control; keep markup-shaped input literal.
function plainNotificationText(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

if (typeof module !== "undefined") {
  module.exports = {
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
    actionIdentity: actionIdentity,
    pruneFired: pruneFired,
    launchableUrl: launchableUrl,
    plainNotificationText: plainNotificationText,
    isOngoing: isOngoing
  }
}
