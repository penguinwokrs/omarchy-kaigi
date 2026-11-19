import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import "Model.js" as Model

// One instance for the whole shell (kind "service"), so notifications and
// auto-join fire once no matter how many monitors draw the bar widget.
//
// It runs bin/kaigi-events once a minute (feeds are refetched every
// `refreshMinutes`; in between the helper reads its cache), ticks every five
// seconds, and claims each due action in ~/.local/state/kaigi/fired.json
// before acting, so a shell restart or plugin reload never repeats one.
Item {
  id: root

  property var shell: null
  property var manifest: null

  readonly property string home: Quickshell.env("HOME")
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")
  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")
  readonly property string configDir: configHome + "/kaigi"
  readonly property string configPath: configDir + "/config.json"
  readonly property string stateDir: stateHome + "/kaigi"
  readonly property string firedPath: stateDir + "/fired.json"
  readonly property string helperPath: decodeURIComponent(String(Qt.resolvedUrl("bin/kaigi-events")).replace(/^file:\/\//, ""))
  readonly property string googlePath: decodeURIComponent(String(Qt.resolvedUrl("bin/kaigi-google")).replace(/^file:\/\//, ""))
  readonly property string launchBrowserPath: decodeURIComponent(String(Qt.resolvedUrl("bin/kaigi-launch-browser")).replace(/^file:\/\//, ""))

  // ---- Google sign-in state (bin/kaigi-google) ----
  property bool googleClient: false
  property var googleAccounts: []
  property string googleState: ""      // "" | "running" | "error"
  property string googleMessage: ""
  // Google UI is relevant when nothing is configured yet or a Google entry exists.
  readonly property bool usesGoogle: {
    var cals = Array.isArray(rawConfig.calendars) ? rawConfig.calendars : []
    if (cals.length === 0) return true
    for (var i = 0; i < cals.length; i++) if (cals[i] && cals[i].type === "google") return true
    return false
  }
  readonly property var googleAuthRequiredAccounts: {
    var out = []
    for (var i = 0; i < errors.length; i++)
      if (errors[i] && errors[i].code === "auth_required" && out.indexOf(String(errors[i].account || "default")) === -1)
        out.push(String(errors[i].account || "default"))
    return out
  }
  readonly property bool googleAuthRequired: googleAuthRequiredAccounts.length > 0

  property var rawConfig: ({})
  property bool configFileExists: false
  property string configError: ""
  readonly property var config: Model.withDefaults(rawConfig)

  property var events: []
  property var errors: []
  property bool configured: false
  property bool loading: false
  property bool loadedOnce: false
  property double lastUpdated: 0
  property double now: Date.now()

  // For the settings window (from bin/kaigi-events).
  property var calendarAccounts: []
  property var feeds: []
  property var chromeProfiles: []
  property var schemeHandlers: null    // { zoommtg: true, msteams: false, ... }
  property var browsers: null          // [{ id, name, exec, urlAt, profiles }]; null until read

  property var fired: ({})
  property bool firedLoaded: false
  property bool stateDirReady: false
  property bool pendingForce: false

  readonly property var nextEvent: Model.nextEvent(events, config, now, false)
  readonly property var nextJoinable: Model.nextEvent(events, config, now, true)

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function refresh(force) {
    if (helper.running) {
      if (force) pendingForce = true
      return
    }
    loading = true
    helper.command = force ? ["python3", "-I", helperPath, "--force", "--config", configPath]
                           : ["python3", "-I", helperPath, "--config", configPath]
    helper.running = true
  }

  function applyOutput(text) {
    var out = null
    try { out = JSON.parse(String(text || "")) } catch (e) { out = null }
    if (!out || typeof out !== "object") {
      root.errors = [{ calendar: "", message: "kaigi-events returned no data" }]
      return
    }
    root.configured = out.configured === true
    root.events = Array.isArray(out.events) ? out.events.slice(0, 500) : []
    root.errors = Array.isArray(out.errors) ? out.errors.slice(0, 20) : []
    root.calendarAccounts = Array.isArray(out.accounts) ? out.accounts.slice(0, 10) : []
    root.feeds = Array.isArray(out.feeds) ? out.feeds.slice(0, 20) : []
    root.chromeProfiles = Array.isArray(out.chromeProfiles) ? out.chromeProfiles.slice(0, 20) : []
    root.schemeHandlers = out.schemeHandlers && typeof out.schemeHandlers === "object" ? out.schemeHandlers : null
    root.browsers = Array.isArray(out.browsers) ? out.browsers.slice(0, 40) : null
    root.lastUpdated = Number(out.generatedAt) || Date.now()
    root.loadedOnce = true
    root.now = Date.now()
    root.runActions()
  }

  // ---- settings -----------------------------------------------------------

  function cloneConfig() {
    try { return JSON.parse(JSON.stringify(root.rawConfig || {})) } catch (e) { return ({}) }
  }

  function writeConfig(next) {
    root.rawConfig = next
    configFile.setText(JSON.stringify(next, null, 2) + "\n")
    // The file can hold iCal feed URLs, which are secrets.
    Util.execArgv(["chmod", "600", root.configPath])
    root.refresh(false)
  }

  function saveConfig(patch) {
    var next = cloneConfig()
    for (var key in patch) next[key] = patch[key]
    writeConfig(next)
  }

  function updateCalendar(index, key, value) {
    var next = cloneConfig()
    if (!Array.isArray(next.calendars) || !next.calendars[index]) return
    next.calendars[index][key] = value
    writeConfig(next)
  }

  // calendarIdsChosen: the list is the user's own choice, so an empty one
  // means no calendars rather than Google's default selection.
  function setCalendarIds(index, ids) {
    var next = cloneConfig()
    if (!Array.isArray(next.calendars) || !next.calendars[index]) return
    next.calendars[index].calendarIds = ids.slice(0, 100)
    next.calendars[index].calendarIdsChosen = true
    writeConfig(next)
  }
  function setCalendarProfile(index, dir) { updateCalendar(index, "chromeProfile", String(dir || "")) }

  // Auto-join for invitations not answered yet. calendarId is a Google
  // calendar's id within the account; pass "" for an iCal feed. Merges into
  // the stored entry so two quick toggles both stick.
  function setPendingAutoJoin(index, calendarId, on) {
    var next = cloneConfig()
    if (!Array.isArray(next.calendars) || !next.calendars[index]) return
    var entry = next.calendars[index]
    if (!calendarId) {
      if (on) delete entry.pendingAutoJoin
      else entry.pendingAutoJoin = false
    } else {
      var map = entry.pendingAutoJoin && typeof entry.pendingAutoJoin === "object" && !Array.isArray(entry.pendingAutoJoin)
        ? entry.pendingAutoJoin : ({})
      if (on) delete map[calendarId]
      else map[calendarId] = false
      if (Object.keys(map).length) entry.pendingAutoJoin = map
      else delete entry.pendingAutoJoin
    }
    writeConfig(next)
  }

  function openConfigFile() {
    Util.execArgv(["bash", "-c", 'f="$1"; mkdir -p "$(dirname "$f")"; [ -e "$f" ] || cp "$2" "$f"; chmod 600 "$f"; exec omarchy-launch-editor "$f"',
                   "kaigi", root.configPath,
                   decodeURIComponent(String(Qt.resolvedUrl("config.example.json")).replace(/^file:\/\//, ""))])
  }

  function openSettings(page) { settingsWindow.open(page || "") }

  SettingsWindow {
    id: settingsWindow
    service: root
  }

  // ---- Google -----------------------------------------------------------

  // One helper command runs at a time. A request made meanwhile waits its
  // turn (Model.googleEnqueue) instead of being dropped. A sign-in waits up
  // to five minutes for the browser to come back, so a request made during
  // that wait ends it: the user gave up on that tab. Once the browser has
  // come back the helper ignores the signal and finishes first.
  property var googleQueue: []
  property bool googleWaitingForBrowser: false

  function googleRun(args) {
    if (googleProc.running) {
      root.googleQueue = Model.googleEnqueue(root.googleQueue, args)
      if (root.googleWaitingForBrowser) googleProc.signal(15)
      return
    }
    root.googleWaitingForBrowser = args[0] === "login"
    root.googleState = "running"
    root.googleMessage = ""
    googleProc.command = ["python3", "-I", googlePath].concat(args)
    googleProc.running = true
  }

  // account "auto" adds a new account keyed by its address.
  function googleLogin(account) { googleRun(["login", "--account", String(account || "auto")]) }
  function googleLogout(account) { googleRun(["logout", "--account", String(account || "default")]) }
  function googleImportClient() { googleRun(["setup"]) }
  function googleRefreshStatus() {
    if (!googleStatusProc.running) googleStatusProc.running = true
  }

  function googleLine(line) {
    var msg = null
    try { msg = JSON.parse(String(line || "")) } catch (e) { return }
    if (!msg || typeof msg !== "object") return
    if (msg.event === "error") {
      root.googleState = "error"
      root.googleMessage = String(msg.message || "").slice(0, 200)
    } else if (msg.event === "open") {
      root.googleMessage = "browser"
    }
  }

  // ---- joining --------------------------------------------------------------

  // How to open a link (Model.openPlan): in a meeting app through its URL
  // scheme, or in the browser. webapp windows use the Chrome profile that
  // holds the right Google sign-in, from chromeProfile in config.json (per
  // calendar or global); without one Chrome uses the profile used last. A
  // service set to a browser of its own opens in it, with that profile too
  // when it is the Chrome the profiles were read from.
  function planFor(event) {
    return event && event.link ? Model.openPlan(event.link, root.config, root.schemeHandlers, root.browsers) : null
  }

  function launchArgv(plan, profile) {
    if (plan.via === "webapp" && /^https?:\/\//.test(plan.url)) {
      var argv = ["omarchy-launch-webapp", plan.url]
      if (/^[A-Za-z0-9 _.-]{1,40}$/.test(String(profile || ""))) argv.push("--profile-directory=" + profile)
      return argv
    }
    if (plan.via === "browser" && plan.browser && /^https?:\/\//.test(plan.url)) {
      var list = root.browsers || []
      for (var i = 0; i < list.length; i++) {
        if (list[i] && list[i].id === plan.browser) {
          var own = Model.browserArgv(list[i], plan.url, profile)
          if (own) return ["bash", root.launchBrowserPath].concat(own)
        }
      }
    }
    return ["xdg-open", plan.url]
  }

  function join(event) {
    var plan = planFor(event)
    if (!plan || !Model.launchableUrl(plan.url)) return false
    // MeetingBar's meetingAppUnavailable message.
    if (plan.unavailable)
      Util.execArgv(["omarchy-notification-send", "--app-name", "Kaigi", "-g", "\uDB80\uDCF0", "-u", "normal",
                     strings.t("appUnavailable.title").arg(plan.unavailable), strings.t("appUnavailable.body")])
    else if (plan.missingBrowser)
      Util.execArgv(["omarchy-notification-send", "--app-name", "Kaigi", "-g", "\uDB80\uDCF0", "-u", "normal",
                     strings.t("browserUnavailable.title").arg(plan.missingBrowser.replace(/\.desktop$/, "")),
                     strings.t("browserUnavailable.body")])
    Util.execArgv(launchArgv(plan, event.browserProfile))
    return true
  }

  function joinNext() {
    return join(root.nextJoinable)
  }

  function joinById(id) {
    for (var i = 0; i < root.events.length; i++)
      if (root.events[i].id === id) return join(root.events[i])
    return false
  }

  // ---- actions --------------------------------------------------------------

  function timeText(ms) {
    return new Date(ms).toLocaleTimeString(Qt.locale(Commons.I18n.formatLocale), "HH:mm")
  }

  readonly property int snoozeSeconds: 300

  // snoozable: add "Remind me in 5 minutes" (start notifications only).
  function notify(event, body, snoozable) {
    // The headline renders as plain text; only the body is markup.
    var title = Model.shortenTitle(event.title, 120, strings.t("noTitle"))
    // A headline that looks like an option flag would be parsed as one.
    if (/^-/.test(title)) title = "⁠" + title
    var argv = ["omarchy-notification-send", "--app-name", "Kaigi", "-g", "\uDB80\uDCF0", "-u", "normal",
                title, Model.plainNotificationText(body)]
    var plan = planFor(event)
    var validId = /^[0-9a-f]{1,64}$/.test(String(event.id))
    // When the chosen browser is gone, Join goes through join() like the
    // panel does, so it says so before opening the default browser.
    if (plan && Model.launchableUrl(plan.url) && plan.missingBrowser && validId)
      argv = argv.concat(["--action", strings.t("join"), "omarchy-shell", "-q", "kaigi", "join", String(event.id)])
    else if (plan && Model.launchableUrl(plan.url))
      argv = argv.concat(["--action", strings.t("join")]).concat(launchArgv(plan, event.browserProfile))
    if (snoozable && /^[0-9a-f]{1,64}$/.test(String(event.id)))
      argv = argv.concat(["--action", strings.t("snooze").arg(root.snoozeSeconds / 60),
                          "omarchy-shell", "-q", "kaigi", "snooze", String(event.id)])
    Util.execArgv(argv)
  }

  function snooze(eventId) {
    var exists = root.events.some(function(e) { return e.id === eventId })
    if (!exists || !root.firedLoaded) return false
    var next = Model.pruneFired(root.fired, root.now)
    next[Model.snoozeKey(eventId)] = Date.now() + root.snoozeSeconds * 1000
    root.fired = next
    saveFired()
    return true
  }

  // omarchy-hook runs ~/.config/omarchy/hooks/<name> and <name>.d/* if they
  // exist. Arguments: title, start and end (ISO 8601), meeting link, calendar.
  function runHook(name, e) {
    Util.execArgv(["omarchy-hook", name, String(e.title || ""), new Date(e.start).toISOString(),
                   new Date(e.end).toISOString(), e.link ? String(e.link.url || "") : "", String(e.calendar || "")])
  }

  function dismissEvent(eventId) {
    saveConfig({ dismissedEvents: Model.withDismissed(root.config.dismissedEvents, eventId, root.events) })
  }

  function restoreDismissed() { saveConfig({ dismissedEvents: [] }) }

  // A link outside the calendar (a new meeting, a bookmark): browser or web
  // app per openMeetingsIn. A web app opens in `profile`, else the global
  // chromeProfile.
  function openUrl(url, profile) {
    if (!Model.launchableUrl(url)) return false
    var webapp = root.config.openMeetingsIn === "webapp" && /^https?:\/\//.test(url)
    Util.execArgv(launchArgv({ via: webapp ? "webapp" : "browser", url: url }, profile || root.config.chromeProfile))
    return true
  }

  // Google accounts a new Meet meeting can be created as (Model.createMeetingAccounts).
  readonly property var createMeetingAccounts: Model.createMeetingAccounts(calendarAccounts, config)

  function newMeetingService(service) {
    var name = String(service || root.config.createMeetingService || "")
    // An unknown name opens Meet (Model.createMeetingUrl).
    return Model.CREATE_MEETING.some(function(c) { return c.service === name }) ? name : "meet"
  }

  // The popup asks which account when a Meet meeting has more than one to
  // choose from.
  function createMeetingNeedsAccount(service) {
    return newMeetingService(service) === "meet" && root.createMeetingAccounts.length > 1
  }

  // email picks the account for Meet; with one account signed in it is used
  // without asking. An address that is not signed in is refused.
  function createMeeting(service, email) {
    var name = newMeetingService(service)
    var accounts = name === "meet" ? root.createMeetingAccounts : []
    var account = accounts.length === 1 && !email ? accounts[0] : null
    if (email) {
      for (var i = 0; i < accounts.length; i++)
        if (accounts[i].email.toLowerCase() === String(email).toLowerCase()) account = accounts[i]
      if (!account) return false
    }
    return openUrl(Model.createMeetingUrl(name, null, account ? account.email : ""), account ? account.profile : "")
  }

  function perform(action) {
    var e = action.event
    var range = timeText(e.start) + " – " + timeText(e.end)
    if (action.kind === "eventStart") {
      notify(e, (e.start > root.now ? strings.t("notify.startsSoon") : strings.t("notify.started")).arg(range), true)
    } else if (action.kind === "eventEnd") {
      notify(e, (e.end > root.now ? strings.t("notify.endsSoon") : strings.t("notify.ended")).arg(range), false)
    } else if (action.kind === "autoJoin") {
      join(e)
    } else if (action.kind === "hookStart") {
      runHook("kaigi-event-start", e)
    } else if (action.kind === "hookEnd") {
      runHook("kaigi-event-end", e)
    }
  }

  function runActions() {
    if (!root.firedLoaded || !root.loadedOnce) return
    var due = Model.dueActions(root.events, root.config, root.now, root.fired)
    var snoozes = Model.dueSnoozes(root.events, root.fired, root.now)
    if (due.length === 0 && snoozes.due.length === 0 && snoozes.stale.length === 0) return
    var next = Model.pruneFired(root.fired, root.now)
    for (var i = 0; i < due.length; i++) next[due[i].identity] = root.now
    for (var k = 0; k < snoozes.due.length; k++) delete next[snoozes.due[k].key]
    for (var s = 0; s < snoozes.stale.length; s++) delete next[snoozes.stale[s]]
    // Claim first, act second.
    root.fired = next
    saveFired()
    for (var j = 0; j < due.length; j++) perform(due[j])
    for (var m = 0; m < snoozes.due.length; m++) {
      var e = snoozes.due[m].event
      var range = timeText(e.start) + " – " + timeText(e.end)
      notify(e, (e.start > root.now ? strings.t("notify.startsSoon") : strings.t("notify.started")).arg(range), true)
    }
  }

  function saveFired() {
    if (!root.stateDirReady) return
    firedFile.setText(JSON.stringify(root.fired) + "\n")
  }

  // ---- files and processes -----------------------------------------------

  FileView {
    id: configFile
    path: root.configPath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      root.configFileExists = true
      try {
        var parsed = JSON.parse(text())
        root.rawConfig = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : ({})
        root.configError = ""
      } catch (e) {
        root.configError = "config.json: " + e.message
      }
      root.refresh(false)
    }
    onLoadFailed: {
      root.configFileExists = false
      root.rawConfig = ({})
      root.refresh(false)
    }
  }

  FileView {
    id: firedFile
    path: root.stateDirReady ? root.firedPath : ""
    printErrors: false
    onLoaded: {
      try {
        var parsed = JSON.parse(text())
        root.fired = parsed && typeof parsed === "object" ? parsed : ({})
      } catch (e) {
        root.fired = ({})
      }
      root.firedLoaded = true
      root.runActions()
    }
    onLoadFailed: {
      root.fired = ({})
      root.firedLoaded = true
      root.runActions()
    }
  }

  Process {
    id: mkStateDir
    // A fresh install has neither folder until the first save or sign-in.
    command: ["mkdir", "-p", "-m", "700", root.stateDir, root.configDir]
    running: true
    onExited: root.stateDirReady = true
  }

  Process {
    id: googleProc
    stdout: SplitParser { onRead: function(line) { root.googleLine(line) } }
    onExited: function(exitCode) {
      root.googleWaitingForBrowser = false
      var next = Model.googleDequeue(root.googleQueue)
      if (next) {
        root.googleQueue = next.rest
        root.googleRun(next.args)
      } else if (exitCode === 0) { root.googleState = ""; root.googleMessage = "" }
      else if (root.googleState === "running") root.googleState = "error"
      // Also between queued commands, so a sign-out shows before a sign-in
      // queued behind it starts waiting for the browser.
      root.googleRefreshStatus()
      root.refresh(true)
    }
  }

  Process {
    id: googleStatusProc
    command: ["python3", "-I", root.googlePath, "status"]
    running: true
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var s = null
        try { s = JSON.parse(String(text || "")) } catch (e) { s = null }
        if (!s) return
        root.googleClient = s.client === true
        root.googleAccounts = Array.isArray(s.accounts) ? s.accounts.slice(0, 10) : []
      }
    }
  }

  Process {
    id: helper
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyOutput(text)
    }
    stderr: StdioCollector { waitForEnd: true }
    onExited: function(exitCode) {
      root.loading = false
      if (exitCode !== 0 && !root.loadedOnce)
        root.errors = [{ calendar: "", message: "kaigi-events exited with " + exitCode }]
      if (root.pendingForce) {
        root.pendingForce = false
        Qt.callLater(function() { root.refresh(true) })
      }
    }
  }

  Timer {
    interval: 60 * 1000
    running: true
    repeat: true
    onTriggered: root.refresh(false)
  }

  Timer {
    interval: 5000
    running: true
    repeat: true
    onTriggered: {
      root.now = Date.now()
      root.runActions()
    }
  }

  ShellIpc {
    target: "kaigi"

    function joinNext(): string { return root.joinNext() ? "ok" : "no joinable meeting" }
    function refresh(): string { root.refresh(true); return "ok" }
    function googleLogin(): string { root.googleLogin(); return "ok" }
    function openSettings(): string { root.openSettings(""); return "ok" }
    function openSettingsPage(page: string): string { root.openSettings(page); return "ok" }
    function closeSettings(): string { settingsWindow.close(); return "ok" }
    // From the start notification's "Remind me again" button.
    function snooze(id: string): string { return root.snooze(id) ? "ok" : "unknown event" }
    // From a notification's Join button when the service's browser is gone.
    function join(id: string): string { return root.joinById(id) ? "ok" : "unknown event" }
    function createMeeting(service: string): string { return root.createMeeting(service, "") ? "ok" : "failed" }
    // A Meet meeting as the signed-in account with this address.
    function createMeetingAs(service: string, email: string): string {
      return root.createMeeting(service, email) ? "ok" : "no Meet account with that address"
    }
    // omarchy-shell kaigi set <key> <json value>, e.g. set eventTimeFormat '"hide"'
    function set(key: string, valueJson: string): string {
      if (!/^[A-Za-z][A-Za-z0-9]{0,60}$/.test(key) || key === "calendars") return "invalid key"
      var value
      try { value = JSON.parse(valueJson) } catch (e) { return "invalid JSON" }
      var patch = {}
      patch[key] = value
      root.saveConfig(patch)
      return "ok"
    }
    function next(): string {
      var e = root.nextEvent
      return e ? JSON.stringify({ title: e.title, start: e.start, end: e.end, link: e.link ? e.link.url : "" }) : ""
    }
  }
}
