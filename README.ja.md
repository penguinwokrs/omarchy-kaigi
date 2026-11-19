# Kaigi for Omarchy

[English](README.md) | 日本語

> 非公式の移植版です。MeetingBar とは関係がなく、MeetingBar の公認も受けていません。

[MeetingBar](https://github.com/leits/MeetingBar) を Omarchy のシェルに移植したものです。
バーに次の会議と開始までの残り時間を表示します。クリックするとその日の予定が並び、
ワンクリックで会議に参加できます。会議の開始と終了の通知も出せて、時間になったら
会議を自動で開くこともできます。

```
 Kaigi テスト定例 あと12分        ← バー（会議中は「… 現在 (残り 25分)」）
┌──────────────────────────────────────┐
│ 󰕧 次のミーティングに参加: Kaigi テスト定例 │
│ 今日  11月16日(月)                    │
│ ▍ 10:00 – 10:30  過去の打ち合わせ       │  （終わった予定は薄く表示）
│ ▍ 12:31 – 13:01  Kaigi テスト定例   󰕧 │
│ ▍ 13:30 – 14:00  ~~辞退した会議~~      │  （辞退した予定は取り消し線）
│ 󰑐 更新   󰒓 設定                       │
└──────────────────────────────────────┘
```

## インストール

Omarchy 4.5 以降が必要です（Omarchy シェルのプラグインの仕組みを使います）。

```bash
omarchy plugin add https://github.com/penguinwokrs/omarchy-kaigi --enable
```

`~/.config/omarchy/plugins/penguinwokrs.kaigi` にインストールされ、ウィジェットが時計の右（`centerEnd`）に置かれます。
更新は `omarchy plugin update penguinwokrs.kaigi`、削除は `omarchy plugin remove penguinwokrs.kaigi` です。
ウィジェットは `omarchy bar move penguinwokrs.kaigi --section right` で移動できます。

コードを触る場合は、好きな場所にクローンしてリンクを張る方法もあります。

```bash
git clone https://github.com/penguinwokrs/omarchy-kaigi.git
cd omarchy-kaigi
./install.sh            # ~/.config/omarchy/plugins にリンクを張って有効にする
./install.sh --remove   # 無効にしてリンクを外す
```

インストールしたら、パネルを開いて下の「Googleでログイン」の手順に進んでください。

## カレンダー：Googleでログイン

Kaigi は Google Calendar API を使い、Kaigi 自身の OAuth クライアント（`bin/google-client.json`）を同梱しています。
パネルを開いて **Googleでログイン** を押し、アカウントを選んで読み取りを許可するだけで使えます。

Kaigi の OAuth クライアントは Google の審査（アプリの確認）を通過しています。
ログインすると、「このアプリは Google で確認されていません」という警告は出ずに、そのまま Google の許可画面が表示されます。

- Kaigi が求めるのは、予定とカレンダー一覧の**読み取りだけ**です。予定を作成・変更・削除することはありません。
- データは Google からあなたのパソコンに直接届きます。作者のサーバーなどには送られません（[プライバシーポリシー](PRIVACY.md)）。

### 任意：自分用の OAuth クライアントを使う（5分ほど）

同梱のクライアントで誰でも使えるので、通常は不要です。自分の Google Cloud のプロジェクトを通してログインしたい場合だけ使ってください。
料金はかかりません。Calendar API は無料で、課金アカウントも要りません。Kaigi が使うのは1日数百リクエストほどで、
上限の100万には遠く届きません。自分で取り込んだクライアントは、同梱のクライアントより優先されます。

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作ります（名前は `kaigi` など）。
2. **API とサービス → ライブラリ → Google Calendar API** を開いて **有効にする** を押します。
3. **API とサービス → OAuth 同意画面** を開きます。
   - **ユーザーの種類**: 個人の Gmail なら「外部」を選びます。Google Workspace のアカウントなら、管理者が許可していれば「内部」で十分です。
   - **アプリ名とメールアドレス**: 何でもかまいません。
   - **スコープ**: 追加しなくて大丈夫です。ログイン時に Kaigi が `calendar.events.readonly`（予定の読み取り）と `calendar.calendarlist.readonly`（カレンダー一覧の読み取り）を求めます。
   - **公開ステータス**: 「外部」の場合は **アプリを公開 → 本番環境** にします。「テスト中」のままだと、7日でログインが切れます。自分で使うだけなら審査は要りません。ただしログイン時に「このアプリは Google で確認されていません」と出るので、「詳細 → … に移動」で進んでください。
   - 本番環境に公開するには、ブランディングのページでホームページとプライバシーポリシーのリンクが必要になることがあります。このリポジトリのURLと [PRIVACY.md](PRIVACY.md) を使えます。
4. **認証情報 → 認証情報を作成 → OAuth クライアント ID** を開き、種類は **デスクトップ アプリ** を選びます。作成したら **JSON をダウンロード** を押します。
5. Kaigi のパネルで **ダウンロードしたJSONを取り込む** を押します。`~/Downloads` にある一番新しいクライアントのJSON（`client_secret_*.json` か `*.apps.googleusercontent.com.json`）を `~/.config/kaigi/google-client.json`（本人だけが読める権限）にコピーします。`bin/kaigi-google setup <ファイル>` でも取り込めます。
6. **Googleでログイン** を押し、開いたブラウザでアカウントを選んでアクセスを許可します。

ログインすると、Kaigi は `config.json` に Google の項目を追加し、Google カレンダーで表示をオンにしている
カレンダーを読み込みます。どのカレンダーを使うかは、設定画面の「カレンダー」タブで選べます。

アカウントは複数追加できます（パネルや設定画面の **アカウントを追加**）。追加したアカウントは
メールアドレスで区別されます。そのアドレスでログインしている Chrome のプロファイルがあれば、
会議を開くプロファイルとして自動で設定されます。

### 仕組み

- **ログイン**: インストール型アプリ向けの OAuth です。`127.0.0.1` へのリダイレクト、PKCE（S256）、ランダムな `state` を使います。権限は予定の読み取り（`calendar.events.readonly`）とカレンダー一覧の読み取り（`calendar.calendarlist.readonly`）だけです。
- **トークン**: リフレッシュトークンは `secret-tool` を通して GNOME キーリングに保存します。キーリングが使えないときだけ、`~/.local/state/kaigi/` の下に本人だけが読めるファイルとして保存します。アクセストークンはディスクに書きません。
- **取得**: `refreshMinutes` ごとに予定を取り直し、`~/.cache/kaigi/` に本人だけが読める形でキャッシュします。`singleEvents=true` を使うので、繰り返しの予定は Google 側で展開されます。
- **会議リンクと出欠**: 会議リンクは `conferenceData` か `hangoutLink` を最優先し、次に場所、説明の順に探します。自分の出欠は `attendees` の中の自分の項目（`self: true`）から読みます。勤務場所の予定は読み飛ばします。
- **ログアウト**: パネルや設定画面の **ログアウト**、または `bin/kaigi-google logout --account <名前>` で、トークンを無効にしてキーリングから消し、キャッシュも削除します。
- **ログインが切れたとき**: Google がログインを拒否した場合（取り消された、テスト中で7日経った など）、そのアカウントだけパネルに **再ログイン** ボタンが出ます。

### ほかの方法：iCal フィード

Google の項目と並べて、あるいは代わりに、`.ics` のURLやファイルを `"calendars"` に追加することもできます。

```json
{ "name": "Work (ics)", "url": "https://…/basic.ics", "color": "#4285f4" }
{ "name": "Local", "path": "~/Calendars/team.ics" }
```

取得するのは `https://` と `webcal://` のURLだけです。この場合、どの参加者が自分かは `emails` で指定します。

## 設定

パネルの **設定** ボタン、または `omarchy-shell kaigi openSettings` で設定画面が開きます。
次のタブがあり、変更はその場で保存されます。

- **一般**: 自動参加、開始と終了の通知とそれぞれのタイミング、会議の開き方
- **カレンダー**: Google アカウント（追加・ログアウト）、アカウントごとに表示するカレンダー、アカウントごとの Chrome プロファイル、iCal フィード、表示する期間
- **表示**: バーの予定タイトル、残り時間、タイトルの文字数、進行中の会議の扱い、「近い予定だけ表示」、メニューのタイトル文字数と終了時刻
- **予定**: 終日の予定、会議リンクのない予定、参加者のいない予定、終わった予定、未返答・仮承諾・辞退した予定
- **詳細**: タイトルのフィルタ、追加の会議リンクのパターン、更新間隔、猶予時間、設定ファイルを開く

設定はすべて `~/.config/kaigi/config.json`（本人だけが読める権限）に保存されます。
スクリプトからは `omarchy-shell kaigi set <キー> <JSON>` で変えられます。
例: `omarchy-shell kaigi set eventTimeFormat '"hide"'`

**動作の設定**（`config.json`）:

| キー | 初期値 | 値 |
|---|---|---|
| `showEventsForPeriod` | `today` | `today`（今日）、`today_tomorrow`（今日と明日） |
| `ongoingEventVisibility` | `showTenMinBeforeNext` | `hideImmediateAfter`、`showTenMinAfter`、`showTenMinBeforeNext` |
| `personalEventsAppereance` | `show_active` | `show_active`、`show_inactive`、`hide`（参加者のいない予定。メニューの表示だけに効く） |
| `allDayEvents` | `show` | `show`、`show_with_meeting_link_only`、`hide` |
| `nonAllDayEvents` | `show` | `show`、`show_inactive_without_meeting_link`、`hide_without_meeting_link` |
| `showPendingEvents` / `showTentativeEvents` | `show` | `show`、`show_inactive`、`hide` |
| `declinedEventsAppereance` | `strikethrough` | `strikethrough`、`hide` |
| `pastEventsAppereance` | `show_inactive` | `show_inactive`、`hide` |
| `joinEventNotification` / `…Time` | `true` / `0` | 開始の N 秒前に通知する |
| `endOfEventNotification` / `…Time` | `true` / `0` | 終了の N 秒前に通知する |
| `automaticEventJoin` / `…Time` | `false` / `0` | 開始の N 秒前に会議を開く。未返答や仮承諾の招待も対象。除きたいときは `showPendingEvents` / `showTentativeEvents` を `hide` にする（メニューからも消える） |
| `actionGraceSeconds` | `300` | スリープ明けなどで時刻を過ぎていても、この秒数以内なら実行する |
| `openMeetingsIn` | `browser` | `browser` は `xdg-open` で既定のブラウザに開く。`webapp` は `omarchy-launch-webapp` で、今いるワークスペースに単独のウィンドウとして開く（Chrome 系ブラウザのみ） |
| `providerOpeningModes` | `{}` | サービスごとの開き方。例: `{"zoom": "zoomApp", "teams": "teamsApp"}`。値は `default`（`openMeetingsIn` に従う）、`browser`、`webapp`、または下の「対応サービス」にあるアプリの指定。アプリが入っていなければブラウザで開く |
| `chromeProfile` | `""` | `webapp` のときに会議を開く Chrome のプロファイルのフォルダ名（`Default`、`Profile 2` など。`chrome://version` で確認できる）。カレンダーごとにも指定できる。空なら最後に使ったプロファイル。Google アカウントをプロファイルで分けている場合に便利 |
| `customRegexes` | `[]` | 追加の会議リンクのパターン。最後に試す |
| `filterEventRegexes` | `[]` | タイトルが一致した予定を隠す |
| `dismissedEvents` | `[]` | 無視する予定のID |

**表示の設定**も `config.json` に入ります。`shell.json` のバーの項目
（`omarchy bar set penguinwokrs.kaigi <キー> <値>`）の値は、`config.json` に設定がないときだけ使われます。

| キー | 初期値 | 値 |
|---|---|---|
| `eventTitleFormat` | `show` | `show`、`generic`、`dot`、`none` |
| `eventTimeFormat` | `show` | `show`、`hide` |
| `statusbarEventTitleLength` | `30` | 5〜55（時計の横に置くなら 30 くらいがちょうどよい） |
| `menuEventTitleLength` | `50` | |
| `showEventEndTime` | `true` | |
| `showEventMaxTimeUntilEventEnabled` / `…Threshold` | `false` / `60` | N 分以内に始まる予定だけ表示する |

## 対応サービス

69種類のサービスの会議リンクを検出します（パターンは `bin/services.json`）。Google Meet、Zoom、Microsoft Teams、Webex、Jitsi、Slack ハドル、Discord、Whereby、Around、Lark / Feishu、StreamYard、Riverside など。Outlook の SafeLinks や Google のリダイレクトは、元のURLに戻してから判定します。

設定画面の「一般 → サービスごとの開き方」で、次のサービスはアプリで開くように指定できます。アプリが入っていないとき（URLスキームの登録がないとき）は通知を出してブラウザで開きます。

| サービス | 指定 | 開き方 | Linux のアプリ |
|---|---|---|---|
| Zoom / ZoomGov | `zoomApp` | `zoommtg://…/join?confno=…` | Zoom 公式の Linux 版 |
| Zoom / ZoomGov | `zoomWebApp` | `https://app.zoom.us/wc/<ID>/start`（ブラウザ版） | 不要 |
| Microsoft Teams | `teamsApp` | `msteams://…` | teams-for-linux など（公式の Linux 版はありません） |
| Jitsi | `jitsiApp` | `jitsi-meet://…` | Jitsi Meet Electron |
| Slack | `slackApp` | `slack://join-huddle?team=…&id=…` | Slack 公式の Linux 版 |
| Riverside | `riversideApp` | `riversidefm://…` | （Linux 版は確認できていません） |
| Tuple | `tupleApp` | `tuple://c/…` | Tuple のアプリ（Linux 版があれば） |
| Facebook Workspace | `workplaceApp` | `workchat://room/?joinurl=…` | （Linux 版は確認できていません） |

イベントに `zoommtg://` のリンクが直接書かれている場合は、そのまま Zoom アプリで開きます（なければ https に戻してブラウザで開く）。`discord://` のリンクは Discord アプリで開きます。どのサービスも `browser` か `webapp` を個別に指定できます。

MeetingBar にある Google Meet の「Meet in One」と「Google Meet PWA」は macOS 専用のため、代わりに `webapp`（Omarchy の Web アプリとして開く）を使ってください。FaceTime と電話番号のリンクも macOS 専用なので、対応していません（FaceTime の https リンクはブラウザで開きます）。

## マウス・キー・IPC

- **バー**: 左クリックでパネルを開く。中クリックで次の会議に参加する。右クリックでカレンダーを取り直す。
- **パネル**: ↑/↓（または k/j）で予定を選び、Enter で参加する。`n` で次の会議に参加、`r` で更新、Esc で閉じる。Enter は予定を選んでいるときだけ効きます。
- **IPC**:
  - `omarchy-shell kaigi joinNext`（キーに割り当てると便利）
  - `omarchy-shell kaigi refresh`
  - `omarchy-shell kaigi next`
  - `omarchy-shell kaigi googleLogin`
  - `omarchy-shell kaigi openSettings`
  - `omarchy-shell kaigi set <キー> <JSON>`
  - `omarchy-shell penguinwokrs.kaigi toggle`

## 仕組み

- `bin/kaigi_google.py` と `bin/kaigi-google` が Google へのログインと Calendar API を担当します。Python の標準ライブラリだけで動きます。
- `bin/kaigi-events` も標準ライブラリだけで動きます。フィードを読み、繰り返しの予定（RRULE、EXDATE、RDATE、RECURRENCE-ID、タイムゾーン、夏時間）を展開し、`bin/services.json` にある69種類のサービスのパターンで会議リンクを探します。会議アプリの URL スキーム（`zoommtg` など）が登録されているかも調べます。結果は JSON で出力します。
- `Service.qml` はシェルに1つだけ常駐します。1分ごとにヘルパーを呼び、5秒ごとに通知や自動参加の時刻を確認します。通知や参加の前に、その操作を `~/.local/state/kaigi/fired.json` に記録します。そのため、モニターが複数あっても、プラグインの再読み込みや `omarchy restart shell` をしても、同じ操作は繰り返されません。
- 開くのは、既知のサービス（または `customRegexes`）に一致した `https`、`http`、`zoommtg`、`discord` のURLと、そこから作った会議アプリ用のURL（`msteams`、`jitsi-meet`、`slack`、`riversidefm`、`tuple`、`workchat`）だけです。URLはシェルを通さず、引数として渡します。
- `Panel.qml` がバーのウィジェットとパネル、`SettingsWindow.qml` が設定画面です。`Model.js` に予定の選び方、表示、タイミングの計算が入っています。

## 開発

プラグインのフォルダ内のファイルを保存すると、バーのウィジェットは自動で読み込み直されます。
`Service.qml` と `SettingsWindow.qml` の変更は、`omarchy restart shell` をするまで反映されません。

## テスト

```bash
python3 -m unittest discover -s tests
TZ=Asia/Tokyo node --test tests/
```

## まだ移植していないもの

この版には、MeetingBar の次の機能はありません。

- macOS のカレンダー（EventKit）連携。Linux で同じことをするなら GNOME Online Accounts
- 全画面のリマインダー
- スヌーズ
- ブックマーク
- AppleScript やショートカットとの連携
- その場での会議の作成
- サービスごとに別のブラウザ（Firefox、Safari など）を選ぶ機能。Kaigi では「既定のブラウザ」か「Webアプリ」を選べます
- メニューのタイムライン
- 予定の詳細のサブメニュー
- メニューから個別の予定を非表示にする機能

## プライバシー

[PRIVACY.md](PRIVACY.md) を参照してください。Kaigi はカレンダーを読み取るだけで、Google の API 以外にはどこにもデータを送りません。

## ライセンス

Apache-2.0 です。MeetingBar から取り入れた部分については `NOTICE` を参照してください。
