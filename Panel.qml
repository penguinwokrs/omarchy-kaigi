import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Bar widget: the next meeting and its countdown, MeetingBar style, plus a
// popup with today's (and optionally tomorrow's) events to join.
//
// Calendar state lives in Service.qml (one per shell); this widget is drawn
// once per monitor and only reads it.
Panel {
  id: root
  moduleName: "penguinwokrs.kaigi"
  ipcTarget: "penguinwokrs.kaigi"

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  readonly property var service: bar && bar.shell && typeof bar.shell.serviceFor === "function"
    ? bar.shell.serviceFor("penguinwokrs.kaigi") : null
  readonly property bool vertical: bar ? bar.vertical : false
  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // ---- display settings (shell.json entry; MeetingBar names) ----
  // Settings window values (config.json) win over the bar entry in shell.json.
  function opt(name, fallback) {
    var raw = service && service.rawConfig ? service.rawConfig[name] : undefined
    return raw === undefined || raw === null ? setting(name, fallback) : raw
  }
  readonly property string eventTitleFormat: opt("eventTitleFormat", "show")
  readonly property string eventTimeFormat: opt("eventTimeFormat", "show")
  readonly property int titleLength: Math.max(5, Math.min(55, Number(opt("statusbarEventTitleLength", 30)) || 30))
  readonly property int menuTitleLength: Math.max(10, Number(opt("menuEventTitleLength", 50)) || 50)
  readonly property bool showEventEndTime: opt("showEventEndTime", true) !== false
  readonly property var displaySettings: ({
    showEventMaxTimeUntilEventEnabled: opt("showEventMaxTimeUntilEventEnabled", false) === true,
    showEventMaxTimeUntilEventThreshold: Number(opt("showEventMaxTimeUntilEventThreshold", 60)) || 60
  })

  // ---- state from the service ----
  property double now: Date.now()
  readonly property var events: service ? service.events : []
  readonly property var config: service ? service.config : Model.withDefaults({})
  readonly property var nextEvent: service ? Model.nextEvent(events, config, now, false) : null
  readonly property var nextJoinable: service ? Model.nextEvent(events, config, now, true) : null
  readonly property string mode: Model.titleMode(nextEvent, displaySettings, now)
  readonly property bool configured: service ? service.configured : false
  readonly property bool googleSignedOut: service ? (service.googleAccounts.length === 0 || service.googleAuthRequired) : true

  function accountEmail(account) {
    var list = service ? service.googleAccounts : []
    for (var i = 0; i < list.length; i++) if (list[i].account === account) return list[i].email || account
    return account
  }
  readonly property bool hasErrors: service ? (service.errors.length > 0 || service.configError !== "") : false

  // Japanese joins the units with nothing ("3時間57分"), and Translations.t()
  // returns the key for an empty string unless it is given a fallback.
  readonly property var units: ({
    day: strings.t("unit.day"), hour: strings.t("unit.hour"),
    minute: strings.t("unit.minute"), separator: strings.t("unit.separator", "")
  })

  function timeText(ms) {
    return new Date(ms).toLocaleTimeString(Qt.locale(Commons.I18n.formatLocale), "HH:mm")
  }

  function eventTitle(event, limit) {
    if (eventTitleFormat === "generic") return strings.t("genericMeeting")
    if (eventTitleFormat === "dot") return "•"
    if (eventTitleFormat === "none") return ""
    return Model.shortenTitle(event.title, limit, strings.t("noTitle"))
  }

  function statusTime(event) {
    var parts = Model.timeLeftParts(event, now)
    var dur = Model.formatDuration(parts, units)
    return (parts.ongoing ? strings.t("status.now") : strings.t("status.in")).arg(dur)
  }

  readonly property string barText: {
    if (vertical || mode !== "nextEvent" || !nextEvent) return ""
    var bits = []
    var t = eventTitle(nextEvent, titleLength)
    if (t) bits.push(t)
    if (eventTimeFormat !== "hide") bits.push(statusTime(nextEvent))
    return bits.join(" ")
  }

  readonly property string tooltip: {
    if (!service) return strings.t("serviceMissing")
    if (!configured || googleSignedOut && events.length === 0) return strings.t("setupHint")
    if (!nextEvent) return strings.t("noUpcoming")
    return Model.shortenTitle(nextEvent.title, 120, strings.t("noTitle")) + "\n"
      + timeText(nextEvent.start) + " – " + timeText(nextEvent.end)
  }

  function join(event) {
    if (service && service.join(event)) close()
  }

  function openSettings() {
    if (service) service.openSettings("")
    close()
  }


  // ---- details ----
  property string expandedId: ""
  function toggleDetails(id) { expandedId = expandedId === id ? "" : id }

  // ---- bookmarks ----
  readonly property var bookmarks: Model.parseBookmarks(config.bookmarks)

  // ---- new meeting ----
  // With several Google accounts signed in, "New meeting" (Meet) first lists
  // them to choose which one to create it as.
  property bool choosingAccount: false
  function newMeeting() {
    if (!service) return
    if (service.createMeetingNeedsAccount("")) choosingAccount = !choosingAccount
    else if (service.createMeeting("", "")) close()
  }

  // ---- keyboard cursor over joinable rows ----
  property int cursor: -1
  readonly property var sections: Model.menuSections(events, config, now)
  readonly property var flatRows: {
    var out = []
    for (var s = 0; s < sections.length; s++)
      for (var r = 0; r < sections[s].rows.length; r++) out.push(sections[s].rows[r])
    return out
  }
  readonly property var flatIds: flatRows.map(function(row) { return row.event.id })

  function moveCursor(dy) {
    if (flatRows.length === 0) { cursor = -1; return }
    if (cursor < 0) { cursor = 0; return }
    cursor = Math.max(0, Math.min(flatRows.length - 1, cursor + dy))
  }

  // Enter joins only the row the keyboard cursor is on: a stray Enter typed
  // while the popup grabs focus must not start a meeting.
  function activateCursor() {
    if (cursor >= 0 && cursor < flatRows.length) join(flatRows[cursor].event)
  }

  onOpenedChanged: {
    cursor = -1
    expandedId = ""
    choosingAccount = false
    if (opened && service) service.refresh(false)
  }

  Timer {
    interval: 5000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.now = Date.now()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.barText !== "" ? root.barText : "󰃭"   // nf-md-calendar
    dimmed: root.barText === "" && (!root.configured || root.hasErrors)
    horizontalMargin: 8.75
    tooltipText: root.opened ? "" : root.tooltip
    pressFeedbackButtons: Qt.NoButton

    onPressed: function(b) {
      if (b === Qt.MiddleButton) { if (root.nextJoinable) root.join(root.nextJoinable) }
      else if (b === Qt.RightButton) { if (root.service) root.service.refresh(true) }
      else root.toggle()
    }
  }

  component PlainText: Text {
    textFormat: Text.PlainText
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    elide: Text.ElideRight
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    centerOnBar: false
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(760))

    content: PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      // Left/right on a row closes/opens its details.
      onMoveRequested: function(dx, dy) {
        if (dx !== 0 && root.cursor >= 0 && root.cursor < root.flatRows.length) {
          var id = root.flatRows[root.cursor].event.id
          root.expandedId = dx > 0 ? id : (root.expandedId === id ? "" : root.expandedId)
        } else root.moveCursor(dy)
      }
      onActivateRequested: root.activateCursor()
      onReturnRequested: root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") { if (root.service) root.service.refresh(true) }
        else if (t === "n" || t === "N") { if (root.nextJoinable) root.join(root.nextJoinable) }
      }

      Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: flick.width
          spacing: Style.space(10)

          // ---- Join next ----
          Button {
            width: parent.width
            visible: !!root.nextJoinable
            leftAlign: true
            iconText: "󰕧" // nf-md-video
            text: root.nextJoinable
              ? strings.t("joinNext").arg(Model.shortenTitle(root.nextJoinable.title, 40, strings.t("noTitle")))
              : ""
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: root.join(root.nextJoinable)
          }

          // ---- Google sign-in ----
          Column {
            width: parent.width
            spacing: Style.space(6)
            visible: !!root.service && root.service.usesGoogle
              && (!root.service.googleClient || root.googleSignedOut || root.service.googleState !== "")

            PlainText {
              width: parent.width
              visible: !!root.service && !root.service.googleClient
              wrapMode: Text.Wrap
              elide: Text.ElideNone
              text: strings.t("google.setupSteps")
            }
            Flow {
              width: parent.width
              spacing: Style.space(6)
              visible: !!root.service && !root.service.googleClient
              Button {
                iconText: "󰊭" // nf-md-google
                text: strings.t("google.openConsole")
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: { Util.execArgv(["xdg-open", "https://console.cloud.google.com/apis/credentials"]); root.close() }
              }
              Button {
                iconText: "󰇚" // nf-md-download
                text: strings.t("google.importClient")
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.service.googleImportClient()
              }
            }
            Button {
              width: parent.width
              visible: !!root.service && root.service.googleClient && root.service.googleAccounts.length === 0
              enabled: !!root.service
              iconText: "󰊭"
              text: strings.t("google.signIn")
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.service.googleLogin("auto")
            }
            Repeater {
              model: root.service && root.service.googleAccounts.length > 0 ? root.service.googleAuthRequiredAccounts : []
              Button {
                required property var modelData
                width: column.width
                enabled: !!root.service
                iconText: "󰊭"
                text: strings.t("google.signInAgainFor").arg(root.accountEmail(modelData))
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.service.googleLogin(modelData)
              }
            }
            PlainText {
              width: parent.width
              visible: !!root.service && root.service.googleState !== ""
              wrapMode: Text.Wrap
              elide: Text.ElideNone
              color: root.service && root.service.googleState === "error" ? (root.bar ? root.bar.urgent : Commons.Color.urgent) : root.dim
              text: !root.service ? ""
                : root.service.googleState === "running" ? strings.t("google.waiting")
                : root.service.googleMessage
            }
          }

          // ---- errors ----
          Repeater {
            model: root.service ? root.service.errors.filter(function(e) { return e && e.code !== "auth_required" && e.code !== "client_missing" })
                                    .concat(root.service.configError ? [{ calendar: "", message: root.service.configError }] : []) : []
            PlainText {
              required property var modelData
              width: column.width
              wrapMode: Text.Wrap
              elide: Text.ElideNone
              color: root.bar ? root.bar.urgent : Commons.Color.urgent
              font.pixelSize: Style.font.bodySmall
              text: (modelData.calendar ? modelData.calendar + ": " : "") + String(modelData.message || "")
            }
          }

          // ---- Today / Tomorrow ----
          Repeater {
            model: root.sections

            Column {
              id: section
              required property var modelData
              required property int index
              width: column.width
              spacing: Style.space(2)

              PanelSectionHeader {
                width: parent.width
                foreground: root.foreground
                fontFamily: root.fontFamily
                text: (section.modelData.key === "today" ? strings.t("today") : strings.t("tomorrow"))
                  + "  " + new Date(section.modelData.dayStart).toLocaleDateString(Qt.locale(Commons.I18n.formatLocale), strings.t("dateFormat"))
              }

              PlainText {
                visible: section.modelData.rows.length === 0
                leftPadding: Style.space(8)
                color: root.dim
                text: strings.t("noEvents")
              }

              Repeater {
                model: section.modelData.rows

                Column {
                  id: entry
                  required property var modelData
                  readonly property var event: modelData.event
                  readonly property var look: modelData.look
                  readonly property bool expanded: root.expandedId === event.id
                  width: section.width
                  spacing: Style.space(2)

                Rectangle {
                  id: row
                  readonly property var event: entry.event
                  readonly property var look: entry.look
                  readonly property int flatIndex: root.flatIds.indexOf(event.id)
                  readonly property bool hot: mouse.containsMouse || (root.cursor >= 0 && root.cursor === flatIndex)
                  width: section.width
                  height: Math.max(Style.spacing.popupRowHeight, rowContent.implicitHeight + Style.space(8))
                  radius: Style.cornerRadius
                  color: hot && look.joinable ? Style.hoverFill : (look.ongoing || entry.expanded ? Style.normalFill : "transparent")
                  opacity: look.inactive ? 0.5 : 1.0

                  Row {
                    id: rowContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Style.space(8)
                    anchors.rightMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(10)

                    Rectangle {
                      width: Style.space(3)
                      height: titleText.implicitHeight
                      anchors.verticalCenter: parent.verticalCenter
                      color: /^#[0-9a-fA-F]{3,8}$/.test(String(row.event.color || "")) ? row.event.color : root.dim
                    }

                    PlainText {
                      id: timeLabel
                      width: Style.space(root.showEventEndTime ? 96 : 44)
                      anchors.verticalCenter: parent.verticalCenter
                      color: root.dim
                      text: row.event.allDay ? strings.t("allDay")
                        : root.timeText(row.event.start) + (root.showEventEndTime ? " – " + root.timeText(row.event.end) : "")
                    }

                    // Title, then "Not answered" for invitations without a
                    // reply. The box keeps the glyphs at the right edge.
                    Item {
                      id: titleBox
                      width: rowContent.width - timeLabel.width - joinGlyph.width - detailsGlyph.width - Style.space(3) - rowContent.spacing * 4
                      height: titleText.implicitHeight
                      anchors.verticalCenter: parent.verticalCenter

                      PlainText {
                        id: titleText
                        width: Math.min(implicitWidth, titleBox.width - (pendingMark.visible ? pendingMark.implicitWidth + Style.space(8) : 0))
                        anchors.verticalCenter: parent.verticalCenter
                        font.strikeout: row.look.declined
                        font.bold: row.look.ongoing
                        text: Model.shortenTitle(row.event.title, root.menuTitleLength, strings.t("noTitle"))
                      }

                      PlainText {
                        id: pendingMark
                        visible: !!row.look.pending
                        anchors.left: titleText.right
                        anchors.leftMargin: Style.space(8)
                        anchors.verticalCenter: parent.verticalCenter
                        elide: Text.ElideNone
                        color: root.dim
                        font.pixelSize: Style.font.bodySmall
                        text: strings.t("pendingMark")
                      }
                    }

                    PlainText {
                      id: joinGlyph
                      width: Style.space(18)
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignRight
                      color: row.hot ? root.foreground : root.dim
                      text: row.look.joinable ? "󰕧" : ""
                    }

                    // Show or hide the details below the row.
                    PlainText {
                      id: detailsGlyph
                      width: Style.space(16)
                      anchors.verticalCenter: parent.verticalCenter
                      horizontalAlignment: Text.AlignHCenter
                      color: detailsMouse.containsMouse || entry.expanded ? root.foreground : root.dim
                      text: entry.expanded ? "󰅃" : "󰅀" // nf-md-chevron_up / chevron_down
                    }
                  }

                  // Click joins a meeting; on a row without a link it opens the details.
                  MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (row.look.joinable) root.join(row.event)
                      else root.toggleDetails(row.event.id)
                    }
                  }

                  MouseArea {
                    id: detailsMouse
                    z: 1
                    width: detailsGlyph.width + Style.space(12)
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleDetails(row.event.id)
                  }

                  PanelToolTip {
                    visible: mouse.containsMouse && !detailsMouse.containsMouse && row.look.joinable
                    text: strings.t("joinVia").arg(String(row.event.link ? row.event.link.serviceName : ""))
                  }
                }

                // ---- details ----
                Column {
                  visible: entry.expanded
                  width: section.width
                  leftPadding: Style.space(21)
                  rightPadding: Style.space(8)
                  bottomPadding: Style.space(6)
                  spacing: Style.space(4)
                  readonly property real textWidth: width - leftPadding - rightPadding

                  PlainText {
                    width: parent.textWidth
                    visible: text !== ""
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    font.pixelSize: Style.font.bodySmall
                    text: entry.expanded && entry.event.location ? "󰍎 " + String(entry.event.location).slice(0, 300) : ""
                  }
                  PlainText {
                    width: parent.textWidth
                    visible: text !== ""
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    font.pixelSize: Style.font.bodySmall
                    color: root.dim
                    text: entry.expanded ? Model.attendeeSummary(entry.event, strings.t("details.attendees"), strings.t("details.more"), 8) : ""
                  }
                  PlainText {
                    width: parent.textWidth
                    visible: text !== ""
                    wrapMode: Text.Wrap
                    elide: Text.ElideRight
                    maximumLineCount: 12
                    font.pixelSize: Style.font.bodySmall
                    text: entry.expanded ? String(entry.event.notes || "") : ""
                  }
                  PlainText {
                    width: parent.textWidth
                    visible: entry.expanded && !entry.event.location && !entry.event.notes && !(entry.event.attendees || []).length
                    font.pixelSize: Style.font.bodySmall
                    color: root.dim
                    text: strings.t("details.none")
                  }
                  Button {
                    iconText: "󰈉" // nf-md-eye_off
                    text: strings.t("details.dismiss")
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                    enabled: !!root.service
                    onClicked: { root.expandedId = ""; root.service.dismissEvent(entry.event.id) }
                  }
                }
                }
              }
            }
          }

          PanelSeparator { width: parent.width; foreground: root.foreground }

          // ---- bookmarks ----
          Column {
            width: parent.width
            spacing: Style.space(2)
            visible: root.bookmarks.length > 0

            PanelSectionHeader {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              text: strings.t("bookmarks")
            }
            Repeater {
              model: root.bookmarks
              Button {
                required property var modelData
                width: column.width
                leftAlign: true
                iconText: "󰃀" // nf-md-bookmark
                text: modelData.name
                foreground: root.foreground
                fontFamily: root.fontFamily
                enabled: !!root.service
                onClicked: { if (root.service.openUrl(modelData.url)) root.close() }
              }
            }
          }

          Row {
            spacing: Style.space(6)
            Button {
              iconText: "󰐕" // nf-md-plus
              text: strings.t("newMeeting")
              foreground: root.foreground
              fontFamily: root.fontFamily
              enabled: !!root.service
              onClicked: root.newMeeting()
            }
            Button {
              iconText: "󰑐" // nf-md-refresh
              text: strings.t("refresh")
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: if (root.service) root.service.refresh(true)
            }
            Button {
              iconText: "󰒓" // nf-md-cog
              text: strings.t("calendars")
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.openSettings()
            }
          }

          // ---- new meeting: which account ----
          Column {
            width: parent.width
            spacing: Style.space(2)
            visible: root.choosingAccount && !!root.service && root.service.createMeetingNeedsAccount("")

            PanelSectionHeader {
              width: parent.width
              foreground: root.foreground
              fontFamily: root.fontFamily
              text: strings.t("newMeeting.chooseAccount")
            }
            Repeater {
              model: root.choosingAccount && root.service ? root.service.createMeetingAccounts : []
              Button {
                required property var modelData
                width: column.width
                leftAlign: true
                iconText: "󰊭" // nf-md-google
                text: modelData.email
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: { if (root.service.createMeeting("", modelData.email)) root.close() }
              }
            }
          }

          PlainText {
            visible: !!root.service && root.service.lastUpdated > 0
            color: root.dim
            font.pixelSize: Style.font.caption
            text: strings.t("updatedAt").arg(root.service ? root.timeText(root.service.lastUpdated) : "")
          }
        }
      }
    }
  }
}
