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

test("auto-join needs a link and skips declined/all-day/personal-hidden", () => {
  const cfg = { automaticEventJoin: true, joinEventNotification: false, endOfEventNotification: false }
  const at = now + 5 * MIN
  const events = [ev(5, 30, { link: null }), ev(5, 30, { participation: "declined" }), ev(5, 30, { allDay: true }),
    ev(5, 30, { hasAttendees: false })]
  assert.equal(M.dueActions(events, cfg, at, {}).length, 1)
  assert.equal(M.dueActions(events, Object.assign({ personalEventsAppereance: "hide" }, cfg), at, {}).length, 0)
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

test("fired identities older than two days are pruned", () => {
  const out = M.pruneFired({ a: now, b: now - 3 * 24 * 60 * MIN }, now)
  assert.deepEqual(Object.keys(out), ["a"])
})
