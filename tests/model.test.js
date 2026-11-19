// Run: TZ=Asia/Tokyo node --test tests/
const test = require("node:test")
const assert = require("node:assert/strict")
const M = require("../Model.js")

const MIN = 60 * 1000
const now = new Date(2026, 10, 16, 10, 0, 0).getTime() // local 10:00
let seq = 0
function ev(startMin, durMin, extra) {
  return Object.assign({
    id: "e" + (++seq), title: "Event " + seq, start: now + startMin * MIN, end: now + (startMin + durMin) * MIN,
    allDay: false, status: "confirmed", participation: "accepted", hasAttendees: true,
    link: { url: "https://meet.google.com/abc-defg-hij", service: "meet", serviceName: "Google Meet" }
  }, extra || {})
}

test("next event skips declined, cancelled, all-day and dismissed", () => {
  const keep = ev(30, 30)
  const events = [ev(5, 30, { participation: "declined" }), ev(6, 30, { status: "cancelled" }),
    ev(-600, 1440, { allDay: true }), ev(7, 30, { id: "gone" }), keep]
  assert.equal(M.nextEvent(events, { dismissedEvents: ["gone"] }, now, false), keep)
})

test("linkRequired skips events without a meeting link", () => {
  const noLink = ev(5, 30, { link: null })
  const withLink = ev(20, 30)
  assert.equal(M.nextEvent([noLink, withLink], {}, now, false), noLink)
  assert.equal(M.nextEvent([noLink, withLink], {}, now, true), withLink)
})

test("ongoing event hands over to the next only within ten minutes", () => {
  const ongoing = ev(-20, 60)
  const soon = ev(9, 30)
  const later = ev(11, 30)
  assert.equal(M.nextEvent([ongoing, later], {}, now, false), ongoing)
  assert.equal(M.nextEvent([ongoing, soon], {}, now, false), soon)
  assert.equal(M.nextEvent([ongoing, later], { ongoingEventVisibility: "hideImmediateAfter" }, now, false), later)
  assert.equal(M.nextEvent([ongoing], { ongoingEventVisibility: "showTenMinAfter" }, now, false), null)
})

test("events ending within a minute and tomorrow's events are out of the today period", () => {
  const ending = ev(-30, 30.5)
  const tomorrow = ev(16 * 60, 30)
  assert.equal(M.nextEvent([ending, tomorrow], {}, now, false), null)
  assert.equal(M.nextEvent([ending, tomorrow], { showEventsForPeriod: "today_tomorrow" }, now, false), tomorrow)
})

test("time left counts from now minus a minute, like MeetingBar", () => {
  assert.deepEqual(M.timeLeftParts(ev(14.5, 30), now), { ongoing: false, days: 0, hours: 0, minutes: 15 })
  assert.deepEqual(M.timeLeftParts(ev(-10, 75), now), { ongoing: true, days: 0, hours: 1, minutes: 6 })
  const units = { day: "%1d", hour: "%1h", minute: "%1m", separator: " " }
  assert.equal(M.formatDuration({ days: 0, hours: 1, minutes: 5 }, units), "1h 5m")
  assert.equal(M.formatDuration({ days: 0, hours: 2, minutes: 0 }, units), "2h")
  assert.equal(M.formatDuration({ days: 0, hours: 0, minutes: 0 }, units), "0m")
  assert.equal(M.formatDuration({ days: 0, hours: 1, minutes: 5 }, { day: "%1日", hour: "%1時間", minute: "%1分", separator: "" }), "1時間5分")
})

test("titles are shortened by characters, not UTF-16 units", () => {
  assert.equal(M.shortenTitle("  Weekly\nsync  ", 55, "No title"), "Weekly sync")
  assert.equal(M.shortenTitle("定例ミーティング（全体）", 5, ""), "定例ミーテ...")
  assert.equal(M.shortenTitle("", 10, "No title"), "No title")
  assert.equal(M.shortenTitle("x", 0, ""), "...")
})

test("title mode honours the max time-until threshold", () => {
  const e = ev(90, 30)
  assert.equal(M.titleMode(null, {}, now), "noUpcoming")
  assert.equal(M.titleMode(e, {}, now), "nextEvent")
  assert.equal(M.titleMode(e, { showEventMaxTimeUntilEventEnabled: true, showEventMaxTimeUntilEventThreshold: 60 }, now), "afterThreshold")
})

test("menu sections sort all-day first and mark past/declined", () => {
  const past = ev(-120, 30)
  const allDay = ev(-600, 1440, { allDay: true, link: null })
  const declined = ev(60, 30, { participation: "declined" })
  const [today] = M.menuSections([declined, past, allDay], {}, now)
  assert.equal(today.key, "today")
  assert.deepEqual(today.rows.map(r => r.event), [allDay, past, declined])
  assert.equal(today.rows[1].look.inactive, true)
  assert.equal(today.rows[2].look.declined, true)
  assert.equal(M.menuSections([declined], { declinedEventsAppereance: "hide" }, now)[0].rows.length, 0)
  assert.equal(M.menuSections([past], { pastEventsAppereance: "hide" }, now)[0].rows.length, 0)
})

test("due actions fire once per identity inside the grace window", () => {
  const e = ev(1, 30)
  const cfg = { automaticEventJoin: true, automaticEventJoinTime: 60 }
  const due = M.dueActions([e], cfg, now, {})
  assert.deepEqual(due.map(d => d.kind), ["autoJoin"])
  const fired = {}
  fired[due[0].identity] = now
  assert.equal(M.dueActions([e], cfg, now, fired).length, 0)
  // At start: start notification (auto-join was claimed already).
  assert.deepEqual(M.dueActions([e], cfg, e.start, fired).map(d => d.kind), ["eventStart"])
  // Long after the grace window nothing fires.
  assert.equal(M.dueActions([e], cfg, e.start + 6 * MIN, {}).filter(d => d.kind !== "eventEnd").length, 0)
  // End notification at end.
  assert.deepEqual(M.dueActions([e], cfg, e.end, fired).map(d => d.kind), ["eventEnd"])
})

test("auto-join follows MeetingBar: link required, declined/all-day skipped, filters only on hide", () => {
  const cfg = { automaticEventJoin: true, joinEventNotification: false, endOfEventNotification: false }
  const at = now + 5 * MIN
  const events = [ev(5, 30, { link: null }), ev(5, 30, { participation: "declined" }), ev(5, 30, { allDay: true }),
    ev(5, 30, { hasAttendees: false })]
  assert.equal(M.dueActions(events, cfg, at, {}).length, 1)
  // personalEventsAppereance is a menu setting only; MeetingBar still auto-joins.
  assert.equal(M.dueActions(events, Object.assign({ personalEventsAppereance: "hide" }, cfg), at, {}).length, 1)
  // Pending invitations auto-join by default, and stop only with showPendingEvents: "hide".
  const pending = [ev(5, 30, { participation: "pending" })]
  assert.equal(M.dueActions(pending, cfg, at, {}).length, 1)
  assert.equal(M.dueActions(pending, Object.assign({ showPendingEvents: "show_inactive" }, cfg), at, {}).length, 1)
  assert.equal(M.dueActions(pending, Object.assign({ showPendingEvents: "hide" }, cfg), at, {}).length, 0)
  const tentative = [ev(5, 30, { participation: "tentative" })]
  assert.equal(M.dueActions(tentative, Object.assign({ showTentativeEvents: "hide" }, cfg), at, {}).length, 0)
})

test("launchable URLs and notification text", () => {
  assert.ok(M.launchableUrl("https://meet.google.com/abc"))
  assert.ok(M.launchableUrl("zoommtg://zoom.us/join?confno=1"))
  assert.ok(!M.launchableUrl("javascript:alert(1)"))
  assert.ok(!M.launchableUrl("file:///etc/passwd"))
  assert.ok(!M.launchableUrl("https://x y"))
  assert.ok(!M.launchableUrl('https://meet.jit.si/Room">Join</a'))
  assert.equal(M.plainNotificationText('<img src="https://t">&'), '&lt;img src="https://t"&gt;&amp;')
})

test("meetings open in the default browser by default, like MeetingBar", () => {
  assert.equal(M.withDefaults({}).openMeetingsIn, "browser")
  assert.equal(M.withDefaults({ openMeetingsIn: "webapp" }).openMeetingsIn, "webapp")
})

test("fired identities older than two days are pruned", () => {
  const out = M.pruneFired({ a: now, b: now - 3 * 24 * 60 * MIN }, now)
  assert.deepEqual(Object.keys(out), ["a"])
})

// --- per-service opening (MeetingBar's MeetingOpener) -----------------------

function plan(service, url, modes, handlers, extra) {
  return M.openPlan({ url: url, service: service }, Object.assign({ providerOpeningModes: modes || {} }, extra || {}), handlers)
}

test("links open in the browser by default, or the web app when chosen", () => {
  assert.deepEqual(plan("meet", "https://meet.google.com/abc-defg-hij"), { url: "https://meet.google.com/abc-defg-hij", via: "browser", unavailable: "" })
  assert.equal(plan("meet", "https://meet.google.com/abc", {}, null, { openMeetingsIn: "webapp" }).via, "webapp")
  assert.equal(plan("meet", "https://meet.google.com/abc", { meet: "browser" }, null, { openMeetingsIn: "webapp" }).via, "browser")
  assert.equal(plan("teams", "https://teams.microsoft.com/l/meetup-join/x", { teams: "webapp" }).via, "webapp")
})

test("Zoom app and web app rewrites match MeetingBar", () => {
  const url = "https://us02web.zoom.us/j/1234567890?pwd=abc"
  assert.deepEqual(plan("zoom", url, { zoom: "zoomApp" }),
    { url: "zoommtg://us02web.zoom.us/join?confno=1234567890&pwd=abc", via: "app", unavailable: "" })
  assert.equal(plan("zoom", url, { zoom: "zoomWebApp" }).url, "https://app.zoom.us/wc/1234567890/start?pwd=abc")
  // Personal rooms stay in the browser.
  assert.equal(plan("zoom", "https://zoom.us/my/someone", { zoom: "zoomApp" }).via, "browser")
  // zoommtg:// links in the event go to the app, or back to https without one.
  const native = "zoommtg://zoom.us/join?confno=123&pwd=x"
  assert.equal(plan("zoom_native", native).via, "app")
  assert.deepEqual(plan("zoom_native", native, {}, { zoommtg: false }),
    { url: "https://zoom.us/j/123?pwd=x", via: "browser", unavailable: "Zoom" })
})

test("other app modes build the native URLs", () => {
  assert.equal(plan("teams", "https://teams.microsoft.com/l/meetup-join/19%3a/0?context=x", { teams: "teamsApp" }).url,
    "msteams://teams.microsoft.com/l/meetup-join/19%3a/0?context=x")
  assert.equal(plan("jitsi", "https://meet.jit.si/Room", { jitsi: "jitsiApp" }).url, "jitsi-meet://meet.jit.si/Room")
  assert.equal(plan("slack", "https://app.slack.com/huddle/T012/C345", { slack: "slackApp" }).url, "slack://join-huddle?team=T012&id=C345")
  assert.equal(plan("tuple", "https://tuple.app/c/abc123", { tuple: "tupleApp" }).url, "tuple://c/abc123")
  assert.equal(plan("riverside", "https://riverside.fm/studio/x", { riverside: "riversideApp" }, { riversidefm: false, "riverside.fm": true }).url,
    "riverside.fm://riverside.fm/studio/x")
  assert.equal(plan("facebook_workspace", "https://acme.workplace.com/groupcall/LINK:abc", { facebook_workspace: "workplaceApp" }).url,
    "workchat://room/?joinurl=https%3A%2F%2Facme.workplace.com%2Fgroupcall%2FLINK%3Aabc")
})

test("a missing app falls back to the browser and names the app", () => {
  assert.deepEqual(plan("teams", "https://teams.microsoft.com/l/meetup-join/x", { teams: "teamsApp" }, { msteams: false }),
    { url: "https://teams.microsoft.com/l/meetup-join/x", via: "browser", unavailable: "Microsoft Teams" })
  // A mode that does not belong to the service is ignored.
  assert.equal(plan("meet", "https://meet.google.com/abc", { meet: "zoomApp" }).url, "https://meet.google.com/abc")
  assert.equal(M.openPlan({ url: "javascript:alert(1)", service: "meet" }, {}, null), null)
  assert.equal(plan("discord", "discord://discord.com/channels/1/2").via, "app")
})

const LOGIN = ["login", "--account", "auto"]
const OUT_A = ["logout", "--account", "a@example.com"]
const OUT_B = ["logout", "--account", "b@example.com"]

test("a request made while the Google helper runs waits instead of being dropped", () => {
  let q = M.googleEnqueue([], OUT_A)
  q = M.googleEnqueue(q, OUT_B)
  assert.deepEqual(q, [OUT_A, OUT_B])
  // A double click waits once.
  assert.deepEqual(M.googleEnqueue(q, ["logout", "--account", "a@example.com"]), [OUT_A, OUT_B])
  // A newer sign-in replaces one that has not started.
  q = M.googleEnqueue(M.googleEnqueue(q, ["login", "--account", "default"]), LOGIN)
  assert.deepEqual(q, [OUT_A, OUT_B, LOGIN])
  assert.deepEqual(M.googleEnqueue(null, ["setup"]), [["setup"]])
})

test("queued Google requests run in order, with a sign-in last", () => {
  let q = [LOGIN, OUT_A, OUT_B]
  const ran = []
  for (let next = M.googleDequeue(q); next; next = M.googleDequeue(q)) {
    ran.push(next.args)
    q = next.rest
  }
  assert.deepEqual(ran, [OUT_A, OUT_B, LOGIN])
  assert.equal(M.googleDequeue([]), null)
  assert.equal(M.googleDequeue(null), null)
  assert.deepEqual(M.googleDequeue([LOGIN]), { args: LOGIN, rest: [] })
})

test("a calendar can stop auto-joining unanswered invitations; notifications still fire", () => {
  const cfg = { automaticEventJoin: true, automaticEventJoinTime: 0, joinEventNotification: true, endOfEventNotification: false }
  const off = ev(5, 30, { participation: "pending", autoJoinPending: false })
  const unset = ev(5, 30, { participation: "pending" })
  const accepted = ev(5, 30, { autoJoinPending: false })
  const at = now + 5 * MIN
  const kinds = (e) => M.dueActions([e], cfg, at, {}).map(d => d.kind).sort()
  assert.deepEqual(kinds(off), ["eventStart"])
  assert.deepEqual(kinds(unset), ["autoJoin", "eventStart"])
  // The setting covers unanswered invitations only.
  assert.deepEqual(kinds(accepted), ["autoJoin", "eventStart"])
})

test("menu rows mark unanswered invitations", () => {
  const pending = ev(60, 30, { participation: "pending" })
  const accepted = ev(90, 30)
  const [today] = M.menuSections([pending, accepted], {}, now)
  assert.deepEqual(today.rows.map(r => r.look.pending), [true, false])
})

test("pending auto-join rows list shown Google calendars and iCal feeds", () => {
  const accounts = [{
    account: "a", email: "a@example.com", configIndex: 0, calendarIds: [], activeIds: ["a@example.com", "team"],
    pendingAutoJoin: { team: false },
    calendars: [{ id: "a@example.com", summary: "Me", primary: true }, { id: "team", summary: "Team" }, { id: "hidden", summary: "Hidden" }]
  }, {
    account: "b", email: "b@example.com", configIndex: 2, calendarIds: ["primary"], activeIds: [],
    calendars: [{ id: "b@example.com", summary: "B", primary: true }, { id: "other", summary: "Other" }]
  }]
  const feeds = [{ configIndex: 1, name: "Holidays", pendingAutoJoin: false }]
  const rows = M.pendingAutoJoinRows(accounts, feeds)
  assert.deepEqual(rows.map(r => [r.index, r.calendarId, r.name, r.owner, r.on]), [
    [0, "a@example.com", "Me", "a@example.com", true],
    [0, "team", "Team", "a@example.com", false],
    [2, "b@example.com", "B", "b@example.com", true],
    [1, "", "Holidays", "", false]
  ])
  assert.deepEqual(M.pendingAutoJoinRows([], []), [])
})

test("hooks run at start and end only when turned on", () => {
  const e = ev(0, 30)
  const base = { joinEventNotification: false, endOfEventNotification: false }
  assert.deepEqual(M.dueActions([e], base, e.start, {}).map(d => d.kind), [])
  const on = Object.assign({ eventHooks: true }, base)
  assert.deepEqual(M.dueActions([e], on, e.start, {}).map(d => d.kind), ["hookStart"])
  assert.deepEqual(M.dueActions([e], on, e.end, {}).map(d => d.kind), ["hookEnd"])
  // Same exclusions as notifications.
  assert.equal(M.dueActions([ev(0, 30, { participation: "declined" })], on, now, {}).length, 0)
})

test("snoozes come due once, and are dropped when the meeting is over or gone", () => {
  const e = ev(0, 30)
  const fired = {}
  fired[M.snoozeKey(e.id)] = now + 5 * MIN
  fired[M.snoozeKey("gone")] = now + 5 * MIN
  let r = M.dueSnoozes([e], fired, now)
  assert.deepEqual([r.due.length, r.stale], [0, [M.snoozeKey("gone")]])
  r = M.dueSnoozes([e], fired, now + 5 * MIN)
  assert.deepEqual(r.due.map(d => d.event), [e])
  r = M.dueSnoozes([e], fired, e.end)
  assert.deepEqual([r.due.length, r.stale.includes(M.snoozeKey(e.id))], [0, true])
  // pruneFired keeps a snooze due in the future.
  assert.ok(M.snoozeKey(e.id) in M.pruneFired(fired, now))
})

test("dismissing keeps ids of listed events and hides the event everywhere", () => {
  const a = ev(10, 30), b = ev(60, 30)
  const list = M.withDismissed(["old", a.id], b.id, [a, b])
  assert.deepEqual(list, [a.id, b.id])
  const cfg = { dismissedEvents: list, automaticEventJoin: true }
  assert.equal(M.menuSections([a, b], cfg, now)[0].rows.length, 0)
  assert.equal(M.dueActions([a], cfg, a.start, {}).length, 0)
})

test("new meeting URLs and bookmarks", () => {
  assert.equal(M.createMeetingUrl("meet"), "https://meet.new")
  assert.equal(M.createMeetingUrl("unknown"), "https://meet.new")
  assert.match(M.createMeetingUrl("jitsi", () => 0), /^https:\/\/meet\.jit\.si\/Kaigi-a{12}$/)
  for (const c of M.CREATE_MEETING) assert.ok(M.launchableUrl(M.createMeetingUrl(c.service)), c.service)
  assert.equal(M.createMeetingUrl("meet", null, "me+x@example.com"), "https://meet.google.com/new?authuser=me%2Bx%40example.com")
  assert.equal(M.createMeetingUrl("zoom", null, "me@example.com"), "https://zoom.us/start/videomeeting")
  assert.ok(M.launchableUrl(M.createMeetingUrl("meet", null, "me@example.com")))
  assert.deepEqual(M.createMeetingAccounts([
    { email: "work@example.com", chromeProfile: "Profile 2" }, { email: "Work@example.com", chromeProfile: "Profile 9" },
    { email: "" }, { email: "me@gmail.com", chromeProfile: "" }, null], { chromeProfile: "Default" }), [
    { email: "work@example.com", profile: "Profile 2" }, { email: "me@gmail.com", profile: "Default" }
  ])
  assert.deepEqual(M.createMeetingAccounts(undefined, {}), [])
  assert.deepEqual(M.parseBookmarks(["Daily standup https://meet.google.com/abc-defg-hij", "https://zoom.us/j/1",
    "no url here", "x javascript:alert(1)", 42]), [
    { name: "Daily standup", url: "https://meet.google.com/abc-defg-hij" },
    { name: "zoom.us/j/1", url: "https://zoom.us/j/1" }
  ])
})

test("attendee summary puts the organizer first and leaves you out", () => {
  const e = ev(0, 30, { attendeeCount: 5, attendees: [
    { name: "Ben", response: "accepted" }, { name: "Me", self: true, response: "pending" },
    { name: "Ana", organizer: true, response: "accepted" }, { name: "Cy", response: "declined" }, { name: "Di" }] })
  assert.equal(M.attendeeSummary(e, "Attendees (%1):", "+%1 more", 2), "Attendees (5): Ana, Ben, +2 more")
  assert.equal(M.attendeeSummary(e, "Attendees (%1):", "+%1 more", 8), "Attendees (5): Ana, Ben, Cy, Di")
  assert.equal(M.attendeeSummary(ev(0, 30), "A (%1):", "+%1", 8), "")
})
