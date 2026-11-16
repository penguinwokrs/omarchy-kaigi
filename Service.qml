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
  readonly property bool googleAuthRequired: {
    for (var i = 0; i < errors.length; i++) if (errors[i] && errors[i].code === "auth_required") return true
    return false
  }

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
    root.lastUpdated = Number(out.generatedAt) || Date.now()
    root.loadedOnce = true
    root.now = Date.now()
    root.runActions()
  }

  // ---- Google -----------------------------------------------------------

  function googleRun(args) {
    if (googleProc.running) return
    root.googleState = "running"
    root.googleMessage = ""
    googleProc.command = ["python3", "-I", googlePath].concat(args)
    googleProc.running = true
  }

  function googleLogin() { googleRun(["login"]) }
  function googleLogout() { googleRun(["logout"]) }
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

  function launchArgv(url) {
    var https = /^https?:\/\//.test(url)
    if (https && root.config.openMeetingsIn !== "browser") return ["omarchy-launch-webapp", url]
    return ["xdg-open", url]
  }

  function join(event) {
    if (!event || !event.link || !Model.launchableUrl(event.link.url)) return false
    Util.execArgv(launchArgv(event.link.url))
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

  function notify(event, body) {
    // The headline renders as plain text; only the body is markup.
    var title = Model.shortenTitle(event.title, 120, strings.t("noTitle"))
    // A headline that looks like an option flag would be parsed as one.
    if (/^-/.test(title)) title = "⁠" + title
    var argv = ["omarchy-notification-send", "--app-name", "Kaigi", "-g", "\uDB80\uDCF0", "-u", "normal",
                title, Model.plainNotificationText(body)]
    if (event.link && Model.launchableUrl(event.link.url))
      argv = argv.concat(["--action", strings.t("join")]).concat(launchArgv(event.link.url))
    Util.execArgv(argv)
  }

  function perform(action) {
    var e = action.event
    var range = timeText(e.start) + " – " + timeText(e.end)
    if (action.kind === "eventStart") {
      notify(e, (e.start > root.now ? strings.t("notify.startsSoon") : strings.t("notify.started")).arg(range))
    } else if (action.kind === "eventEnd") {
      notify(e, (e.end > root.now ? strings.t("notify.endsSoon") : strings.t("notify.ended")).arg(range))
    } else if (action.kind === "autoJoin") {
      join(e)
    }
  }

  function runActions() {
    if (!root.firedLoaded || !root.loadedOnce) return
    var due = Model.dueActions(root.events, root.config, root.now, root.fired)
    if (due.length === 0) return
    var next = Model.pruneFired(root.fired, root.now)
    for (var i = 0; i < due.length; i++) next[due[i].identity] = root.now
    // Claim first, act second.
    root.fired = next
    saveFired()
    for (var j = 0; j < due.length; j++) perform(due[j])
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
    command: ["mkdir", "-p", "-m", "700", root.stateDir]
    running: true
    onExited: root.stateDirReady = true
  }

  Process {
    id: googleProc
    stdout: SplitParser { onRead: function(line) { root.googleLine(line) } }
    onExited: function(exitCode) {
      if (exitCode === 0) { root.googleState = ""; root.googleMessage = "" }
      else if (root.googleState === "running") root.googleState = "error"
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
    function next(): string {
      var e = root.nextEvent
      return e ? JSON.stringify({ title: e.title, start: e.start, end: e.end, link: e.link ? e.link.url : "" }) : ""
    }
  }
}
