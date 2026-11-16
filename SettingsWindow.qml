import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Kaigi's Preferences window, laid out like MeetingBar's Preferences: General,
// Calendars, Appearance, Events and Advanced. Every control writes
// ~/.config/kaigi/config.json through the service at once; there is no Save
// button. Hosted by Service.qml, so there is one window however many bars.
Item {
  id: root

  property var service: null
  property bool opened: false
  property string tab: "general"

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  readonly property var cfg: service ? service.config : ({})
  readonly property color fg: Commons.Color.popups.text
  readonly property color dim: Qt.darker(fg, 1.55)
  readonly property color urgent: Commons.Color.urgent
  readonly property string fontFamily: Style.font.family
  readonly property int rowWidth: Math.max(Style.space(280), Math.min(Style.space(500), flick.width - Style.space(24)))

  function open(page) {
    if (page) root.tab = page
    root.opened = true
    if (service) service.refresh(true)
    Qt.callLater(function() { if (root.opened) keys.forceActiveFocus() })
  }

  function close() { root.opened = false }

  function set(key, value) {
    var patch = {}
    patch[key] = value
    if (service) service.saveConfig(patch)
  }

  function str(key) { return String(cfg[key] === undefined || cfg[key] === null ? "" : cfg[key]) }
  function num(key, fallback) { var n = Number(cfg[key]); return isFinite(n) ? n : fallback }
  function on(key, fallback) { return cfg[key] === undefined ? fallback : cfg[key] === true }

  readonly property var timingStart: [
    { value: "0", label: strings.t("settings.atStart") },
    { value: "60", label: strings.t("settings.minBefore").arg(1) },
    { value: "120", label: strings.t("settings.minBefore").arg(2) },
    { value: "180", label: strings.t("settings.minBefore").arg(3) },
    { value: "300", label: strings.t("settings.minBefore").arg(5) },
    { value: "600", label: strings.t("settings.minBefore").arg(10) }
  ]
  readonly property var timingEnd: [
    { value: "0", label: strings.t("settings.atEnd") },
    { value: "60", label: strings.t("settings.minBefore").arg(1) },
    { value: "120", label: strings.t("settings.minBefore").arg(2) },
    { value: "180", label: strings.t("settings.minBefore").arg(3) },
    { value: "300", label: strings.t("settings.minBefore").arg(5) },
    { value: "600", label: strings.t("settings.minBefore").arg(10) }
  ]
  readonly property var profileOptions: {
    var out = [{ value: "", label: strings.t("settings.profileLastUsed") }]
    var list = service ? service.chromeProfiles : []
    for (var i = 0; i < list.length; i++)
      out.push({ value: list[i].dir, label: (list[i].name || list[i].dir) + (list[i].email ? " · " + list[i].email : "") })
    return out
  }
  readonly property var tabs: [
    { id: "general", icon: "\uDB81\uDC93", label: strings.t("settings.tab.general") },
    { id: "calendars", icon: "\uDB80\uDCED", label: strings.t("settings.tab.calendars") },
    { id: "appearance", icon: "\uDB80\uDFD8", label: strings.t("settings.tab.appearance") },
    { id: "events", icon: "\uDB80\uDE33", label: strings.t("settings.tab.events") },
    { id: "advanced", icon: "\uDB82\uDFA8", label: strings.t("settings.tab.advanced") }
  ]

  // ---- building blocks ------------------------------------------------------

  component Heading: Text {
    textFormat: Text.PlainText
    color: root.fg
    font.family: root.fontFamily
    font.pixelSize: Style.font.title
    font.bold: true
    topPadding: Style.space(10)
  }

  component Note: Text {
    textFormat: Text.PlainText
    width: root.rowWidth
    color: root.dim
    wrapMode: Text.Wrap
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  component SwitchRow: Toggle {
    property string key: ""
    objectName: "switch:" + key
    property bool fallback: false
    width: root.rowWidth
    checked: root.on(key, fallback)
    foreground: root.fg
    fontFamily: root.fontFamily
    onClicked: root.set(key, !checked)
  }

  component ChoiceRow: Dropdown {
    opacity: enabled ? 1 : 0.4
    property string key: ""
    objectName: "choice:" + key
    property bool numeric: false
    width: root.rowWidth
    value: root.str(key)
    foreground: root.fg
    fontFamily: root.fontFamily
    onChanged: function(v) { root.set(key, numeric ? Number(v) : v) }
  }

  component NumberRow: NumberField {
    opacity: enabled ? 1 : 0.4
    property string key: ""
    objectName: "number:" + key
    property int fallback: 0
    value: root.num(key, fallback)
    foreground: root.fg
    fontFamily: root.fontFamily
    onModified: function(v) { root.set(key, v) }
  }

  component ListEditor: Column {
    id: editor
    property string key: ""
    property string title: ""
    property string hint: ""
    width: root.rowWidth
    spacing: Style.space(4)
    Text {
      textFormat: Text.PlainText
      text: editor.title
      color: root.fg
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }
    Rectangle {
      width: parent.width
      height: Style.space(84)
      color: "transparent"
      border.color: area.activeFocus ? Commons.Color.accent : Qt.darker(root.fg, 2.2)
      border.width: 1
      radius: Style.cornerRadius
      ScrollView {
        anchors.fill: parent
        anchors.margins: Style.space(6)
        TextArea {
          id: area
          objectName: "list:" + editor.key
          textFormat: TextEdit.PlainText
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: TextEdit.NoWrap
          placeholderText: editor.hint
          placeholderTextColor: Qt.darker(root.fg, 2.2)
          background: null
          text: (Array.isArray(root.cfg[editor.key]) ? root.cfg[editor.key] : []).join("\n")
          onActiveFocusChanged: if (!activeFocus) {
            var lines = text.split("\n").map(function(l) { return l.trim() }).filter(function(l) { return l !== "" })
            root.set(editor.key, lines.slice(0, 50))
          }
        }
      }
    }
  }

  // ---- window ---------------------------------------------------------------

  OverlayWindow {
    shown: root.opened
    WlrLayershell.namespace: "kaigi-settings"

    Rectangle {
      anchors.fill: parent
      color: Qt.rgba(0, 0, 0, 0.55)
      MouseArea { anchors.fill: parent; onClicked: root.close() }
    }

    Item {
      id: keys
      anchors.fill: parent
      focus: true
      Keys.onEscapePressed: root.close()

      Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(parent.width - Style.space(48), Style.space(760))
        height: Math.min(parent.height - Style.space(48), Style.space(620))
        color: Commons.Color.popups.background
        border.color: Commons.Color.popups.border
        border.width: Math.max(1, Style.normalBorderWidth)
        radius: Style.cornerRadius

        MouseArea { anchors.fill: parent; onClicked: keys.forceActiveFocus() }

        RowLayout {
          anchors.fill: parent
          anchors.margins: Style.space(18)
          spacing: Style.space(18)

          ColumnLayout {
            Layout.preferredWidth: Style.space(170)
            Layout.minimumWidth: Style.space(170)
            Layout.maximumWidth: Style.space(170)
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: Style.space(4)

            Text {
              textFormat: Text.PlainText
              text: strings.t("settings.title")
              color: root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.heading
              font.bold: true
              Layout.bottomMargin: Style.space(10)
            }
            Repeater {
              model: root.tabs
              Button {
                required property var modelData
                Layout.fillWidth: true
                leftAlign: true
                iconText: modelData.icon
                text: modelData.label
                selected: root.tab === modelData.id
                foreground: root.fg
                fontFamily: root.fontFamily
                onClicked: root.tab = modelData.id
              }
            }
            Item { Layout.fillHeight: true }
            Button {
              Layout.fillWidth: true
              leftAlign: true
              iconText: "\uDB80\uDD56"
              text: strings.t("settings.close")
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: root.close()
            }
          }

          Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 1
            color: Qt.darker(root.fg, 2.6)
          }

          Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.minimumWidth: Style.space(300)
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: page.implicitHeight + Style.space(24)
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Loader {
              id: page
              width: flick.width
              sourceComponent: root.tab === "calendars" ? calendarsPage
                : root.tab === "appearance" ? appearancePage
                : root.tab === "events" ? eventsPage
                : root.tab === "advanced" ? advancedPage
                : generalPage
              onLoaded: flick.contentY = 0
            }
          }
        }
      }
    }
  }

  // ---- pages ----------------------------------------------------------------

  Component {
    id: generalPage
    Column {
      spacing: Style.space(8)

      Heading { text: strings.t("settings.autoJoin") }
      SwitchRow { key: "automaticEventJoin"; label: strings.t("settings.autoJoin.label"); description: strings.t("settings.autoJoin.desc") }
      ChoiceRow { key: "automaticEventJoinTime"; numeric: true; label: strings.t("settings.when.join"); options: root.timingStart; enabled: root.on("automaticEventJoin", false) }

      Heading { text: strings.t("settings.notifications") }
      SwitchRow { key: "joinEventNotification"; fallback: true; label: strings.t("settings.notifyStart") }
      ChoiceRow { key: "joinEventNotificationTime"; numeric: true; label: strings.t("settings.when.start"); options: root.timingStart; enabled: root.on("joinEventNotification", true) }
      SwitchRow { key: "endOfEventNotification"; fallback: true; label: strings.t("settings.notifyEnd") }
      ChoiceRow { key: "endOfEventNotificationTime"; numeric: true; label: strings.t("settings.when.end"); options: root.timingEnd; enabled: root.on("endOfEventNotification", true) }
      Note { text: strings.t("settings.actionsNote") }

      Heading { text: strings.t("settings.openMeetings") }
      ChoiceRow {
        key: "openMeetingsIn"
        label: strings.t("settings.openIn")
        options: [{ value: "webapp", label: strings.t("settings.openIn.webapp") }, { value: "browser", label: strings.t("settings.openIn.browser") }]
      }
      ChoiceRow { key: "chromeProfile"; label: strings.t("settings.defaultProfile"); options: root.profileOptions; enabled: root.str("openMeetingsIn") !== "browser" }
      Note { text: strings.t("settings.profileNote") }
    }
  }

  Component {
    id: calendarsPage
    Column {
      spacing: Style.space(8)

      Heading { text: strings.t("settings.googleAccounts") }
      Note {
        visible: !!root.service && !root.service.googleClient
        text: strings.t("google.setupSteps")
      }
      Repeater {
        model: root.service ? root.service.calendarAccounts : []
        Column {
          id: acct
          required property var modelData
          readonly property var effective: modelData.calendarIds && modelData.calendarIds.length ? modelData.calendarIds : modelData.activeIds
          width: root.rowWidth
          spacing: Style.space(4)

          Item {
            width: parent.width
            height: Math.max(acctName.implicitHeight, signOut.implicitHeight)
            Text {
              id: acctName
              anchors.left: parent.left
              anchors.right: signOut.left
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: String(acct.modelData.email || acct.modelData.account)
              color: root.service && root.service.googleAuthRequiredAccounts.indexOf(acct.modelData.account) !== -1 ? root.urgent : root.fg
              font.family: root.fontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
            }
            Button {
              id: signOut
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "\uDB80\uDF43"
              text: strings.t("google.signOut")
              foreground: root.fg
              fontFamily: root.fontFamily
              enabled: root.service ? root.service.googleState !== "running" : false
              onClicked: root.service.googleLogout(acct.modelData.account)
            }
          }
          Note {
            visible: acct.modelData.calendars.length === 0
            text: strings.t("settings.noCalendarsYet")
          }
          Repeater {
            model: acct.modelData.calendars
            Toggle {
              required property var modelData
              objectName: "calendar:" + acct.modelData.account + ":" + modelData.id
              width: root.rowWidth
              label: String(modelData.summary || modelData.id)
              description: modelData.primary ? strings.t("settings.primary") : ""
              checked: acct.effective.indexOf(modelData.id) !== -1
              foreground: root.fg
              fontFamily: root.fontFamily
              onClicked: {
                var ids = acct.effective.slice()
                var at = ids.indexOf(modelData.id)
                if (at === -1) ids.push(modelData.id)
                else ids.splice(at, 1)
                root.service.setCalendarIds(acct.modelData.configIndex, ids)
              }
            }
          }
          Dropdown {
            objectName: "profile:" + acct.modelData.account
            width: root.rowWidth
            label: strings.t("settings.accountProfile")
            value: String(acct.modelData.chromeProfile || "")
            options: root.profileOptions
            foreground: root.fg
            fontFamily: root.fontFamily
            onChanged: function(v) { root.service.setCalendarProfile(acct.modelData.configIndex, v) }
          }
          Item { width: 1; height: Style.space(8) }
        }
      }
      Button {
        visible: !!root.service && root.service.googleClient
        iconText: "\uDB81\uDC15"
        text: strings.t("google.addAccount")
        foreground: root.fg
        fontFamily: root.fontFamily
        enabled: root.service ? root.service.googleState !== "running" : false
        onClicked: root.service.googleLogin("auto")
      }
      Note {
        visible: !!root.service && root.service.googleState !== ""
        color: root.service && root.service.googleState === "error" ? root.urgent : root.dim
        text: !root.service ? "" : root.service.googleState === "running" ? strings.t("google.waiting") : root.service.googleMessage
      }

      Heading {
        text: strings.t("settings.feeds")
        visible: !!root.service && root.service.feeds.length > 0
      }
      Repeater {
        model: root.service ? root.service.feeds : []
        Text {
          required property var modelData
          textFormat: Text.PlainText
          text: "• " + modelData.name + "  (" + (modelData.kind === "file" ? strings.t("settings.feedFile") : "iCal URL") + ")"
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }
      }

      Heading { text: strings.t("settings.period") }
      ButtonGroup {
        objectName: "period"
        value: root.str("showEventsForPeriod") || "today"
        options: [{ value: "today", label: strings.t("today") }, { value: "today_tomorrow", label: strings.t("settings.todayTomorrow") }]
        foreground: root.fg
        fontFamily: root.fontFamily
        onChanged: function(v) { root.set("showEventsForPeriod", v) }
      }
    }
  }

  Component {
    id: appearancePage
    Column {
      spacing: Style.space(8)

      Heading { text: strings.t("settings.bar") }
      ChoiceRow {
        key: "eventTitleFormat"
        label: strings.t("settings.titleFormat")
        options: [
          { value: "show", label: strings.t("settings.titleFormat.show") },
          { value: "generic", label: strings.t("settings.titleFormat.generic") },
          { value: "dot", label: strings.t("settings.titleFormat.dot") },
          { value: "none", label: strings.t("settings.titleFormat.none") }
        ]
      }
      NumberRow { key: "statusbarEventTitleLength"; fallback: 30; from: 5; to: 55; label: strings.t("settings.titleLength") }
      ChoiceRow {
        key: "eventTimeFormat"
        label: strings.t("settings.timeFormat")
        options: [{ value: "show", label: strings.t("settings.timeFormat.show") }, { value: "hide", label: strings.t("settings.timeFormat.hide") }]
      }
      ChoiceRow {
        key: "ongoingEventVisibility"
        label: strings.t("settings.ongoing")
        options: [
          { value: "showTenMinBeforeNext", label: strings.t("settings.ongoing.beforeNext") },
          { value: "showTenMinAfter", label: strings.t("settings.ongoing.tenAfter") },
          { value: "hideImmediateAfter", label: strings.t("settings.ongoing.hide") }
        ]
      }
      SwitchRow { key: "showEventMaxTimeUntilEventEnabled"; label: strings.t("settings.onlySoon"); description: strings.t("settings.onlySoon.desc") }
      NumberRow {
        key: "showEventMaxTimeUntilEventThreshold"; fallback: 60; from: 5; to: 720; stepSize: 5
        label: strings.t("settings.onlySoon.minutes")
        enabled: root.on("showEventMaxTimeUntilEventEnabled", false)
      }

      Heading { text: strings.t("settings.menu") }
      NumberRow { key: "menuEventTitleLength"; fallback: 50; from: 10; to: 120; label: strings.t("settings.menuTitleLength") }
      SwitchRow { key: "showEventEndTime"; fallback: true; label: strings.t("settings.showEndTime") }
    }
  }

  Component {
    id: eventsPage
    Column {
      spacing: Style.space(8)

      Note { text: strings.t("settings.eventsNote") }
      Heading { text: strings.t("settings.byType") }
      ChoiceRow {
        key: "allDayEvents"
        label: strings.t("settings.allDay")
        options: [
          { value: "show", label: strings.t("settings.show") },
          { value: "show_with_meeting_link_only", label: strings.t("settings.withLinkOnly") },
          { value: "hide", label: strings.t("settings.hide") }
        ]
      }
      ChoiceRow {
        key: "nonAllDayEvents"
        label: strings.t("settings.noLink")
        options: [
          { value: "show", label: strings.t("settings.show") },
          { value: "show_inactive_without_meeting_link", label: strings.t("settings.inactive") },
          { value: "hide_without_meeting_link", label: strings.t("settings.hide") }
        ]
      }
      ChoiceRow {
        key: "personalEventsAppereance"
        label: strings.t("settings.personal")
        options: [
          { value: "show_active", label: strings.t("settings.show") },
          { value: "show_inactive", label: strings.t("settings.inactive") },
          { value: "hide", label: strings.t("settings.hideMenuOnly") }
        ]
      }
      ChoiceRow {
        key: "pastEventsAppereance"
        label: strings.t("settings.past")
        options: [{ value: "show_inactive", label: strings.t("settings.inactive") }, { value: "hide", label: strings.t("settings.hide") }]
      }

      Heading { text: strings.t("settings.byResponse") }
      ChoiceRow {
        key: "showPendingEvents"
        label: strings.t("settings.pending")
        options: [
          { value: "show", label: strings.t("settings.show") },
          { value: "show_inactive", label: strings.t("settings.inactive") },
          { value: "hide", label: strings.t("settings.hide") }
        ]
      }
      ChoiceRow {
        key: "showTentativeEvents"
        label: strings.t("settings.tentative")
        options: [
          { value: "show", label: strings.t("settings.show") },
          { value: "show_inactive", label: strings.t("settings.inactive") },
          { value: "hide", label: strings.t("settings.hide") }
        ]
      }
      ChoiceRow {
        key: "declinedEventsAppereance"
        label: strings.t("settings.declined")
        options: [{ value: "strikethrough", label: strings.t("settings.strikethrough") }, { value: "hide", label: strings.t("settings.hide") }]
      }
    }
  }

  Component {
    id: advancedPage
    Column {
      spacing: Style.space(8)

      Heading { text: strings.t("settings.filters") }
      ListEditor { key: "filterEventRegexes"; title: strings.t("settings.filterRegexes"); hint: "^Lunch$" }
      ListEditor { key: "customRegexes"; title: strings.t("settings.customRegexes"); hint: "https://meet\\.example\\.com/\\S+" }
      Note { text: strings.t("settings.regexNote") }

      Heading { text: strings.t("settings.sync") }
      NumberRow { key: "refreshMinutes"; fallback: 5; from: 1; to: 60; label: strings.t("settings.refreshMinutes") }
      NumberRow { key: "actionGraceSeconds"; fallback: 300; from: 0; to: 3600; stepSize: 30; label: strings.t("settings.grace") }
      Note { text: strings.t("settings.graceNote") }

      Heading { text: strings.t("settings.files") }
      Row {
        spacing: Style.space(6)
        Button {
          iconText: "\uDB81\uDC50"
          text: strings.t("refresh")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: if (root.service) root.service.refresh(true)
        }
        Button {
          iconText: "\uDB80\uDE19"
          text: strings.t("settings.openConfigFile")
          foreground: root.fg
          fontFamily: root.fontFamily
          onClicked: { if (root.service) root.service.openConfigFile(); root.close() }
        }
      }
      Repeater {
        model: root.service ? root.service.errors : []
        Note {
          required property var modelData
          color: root.urgent
          text: (modelData.calendar ? modelData.calendar + ": " : "") + String(modelData.message || "")
        }
      }
    }
  }
}
