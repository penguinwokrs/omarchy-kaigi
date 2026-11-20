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
│ ▍ 15:00 – 15:30  採用面接  未返答   󰕧 │  （未返答の招待には目印）
│ 󰑐 更新   󰒓 設定                       │
└──────────────────────────────────────┘
```

## インストール

Omarchy 4.5 以降（Omarchy シェルのプラグインの仕組みを使います）と、`python3`（標準ライブラリだけを使います）が必要です。Google のログインのトークンを GNOME キーリングに保存するには、`secret-tool`（`libsecret` パッケージ）も使います。ない場合は、本人だけが読めるファイルに保存します。どちらも Omarchy に入っています。

```bash
omarchy plugin add https://github.com/penguinwokrs/omarchy-kaigi --enable
```

`~/.config/omarchy/plugins/penguinwokrs.kaigi` にインストールされ、ウィジェットが時計の右（`centerEnd`）に置かれます。
更新は `omarchy plugin update penguinwokrs.kaigi`、削除は `omarchy plugin remove penguinwokrs.kaigi` です。
削除する前に、設定画面の「カレンダー」タブで Google アカウントからログアウトしてください。トークンが無効になり、キーリングからも消えます。そのあと `~/.config/kaigi`、`~/.local/state/kaigi`、`~/.cache/kaigi` を削除します。ログアウトせずに削除した場合は、`secret-tool clear service kaigi-google` でキーリングのトークンを消し、<https://myaccount.google.com/permissions> で Kaigi のアクセスを取り消してください。
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

最初のアカウントでログインするまでは、パネルに **Googleでログイン** が表示されます。2つ目以降のアカウントは、設定画面の「カレンダー」タブの **アカウントを追加** で追加できます。追加したアカウントは
メールアドレスで区別されます。`webapp` のとき、各アカウントの会議はそのアドレスでログインしている Chrome のプロファイルで開きます。そのアカウントで Chrome にログインしているプロファイルを優先し、なければ Google にログインしているプロファイル（最近使ったものから）を使います。カレンダーを読み込むたびに、`authuser` の番号ではなくメールアドレスで探し直すので、アカウントのログイン・ログアウトやプロファイル間の移動があっても追従します。どのプロファイルを使っているかは「カレンダー」タブに表示されます。

### 仕組み

- **ログイン**: インストール型アプリ向けの OAuth です。`127.0.0.1` へのリダイレクト、PKCE（S256）、ランダムな `state` を使います。権限は予定の読み取り（`calendar.events.readonly`）とカレンダー一覧の読み取り（`calendar.calendarlist.readonly`）だけです。
- **トークン**: リフレッシュトークンは `secret-tool` を通して GNOME キーリングに保存します。キーリングが使えないときだけ、`~/.local/state/kaigi/` の下に本人だけが読めるファイルとして保存します。アクセストークンはディスクに書きません。
- **取得**: `refreshMinutes` ごとに予定を取り直し、`~/.cache/kaigi/` に本人だけが読める形でキャッシュします。`singleEvents=true` を使うので、繰り返しの予定は Google 側で展開されます。
- **会議リンクと出欠**: 会議リンクは `conferenceData` か `hangoutLink` を最優先し、次に場所、説明の順に探します。自分の出欠は `attendees` の中の自分の項目（`self: true`）から読みます。勤務場所の予定は読み飛ばします。
- **ログアウト**: 設定画面の「カレンダー」タブの **ログアウト**、または `bin/kaigi-google logout --account <名前>` で、トークンを無効にしてキーリングから消し、キャッシュも削除します。無効化もキーリングからの削除も確認できなかったとき（キーリングに接続できないときを含む）は、アカウントを残したままエラーを表示するので、やり直せます。無効化だけ確認できなかったとき（オフラインなど）は、このパソコンからはトークンとアカウントを消したうえで、Google 側でアクセスを取り消すよう案内します。
- **ログインが切れたとき**: Google がログインを拒否した場合（取り消された、テスト中で7日経った など）、そのアカウントだけパネルに **再ログイン** ボタンが出ます。

### ほかの方法：iCal フィード

Google の項目と並べて、あるいは代わりに、`.ics` のURLやファイルを `"calendars"` に追加することもできます。

```json
{ "name": "Work (ics)", "url": "https://…/basic.ics", "color": "#4285f4" }
{ "name": "Local", "path": "~/Calendars/team.ics" }
```

取得するのは `https://` と `webcal://` のURLだけです。この場合、どの参加者が自分かは `emails` で指定します。

### 未返答の招待の自動参加

自動参加は、まだ返答していない招待も開きます。一部のカレンダーだけ開かないようにするには、設定画面の「一般 → 未返答の招待も自動で開くカレンダー」でそのカレンダーをオフにします。
Google のカレンダー1つずつと iCal フィード1本ずつにスイッチがあり、設定していないカレンダーはオンのままです。
オフにしても止まるのは自動参加だけで、開始と終了の通知は届きます。

`config.json` では、カレンダーの項目の `pendingAutoJoin` です。Google の項目では `{"<カレンダー ID>": false}`、iCal フィードでは `false` を指定します。

```json
{ "type": "google", "account": "me@example.com", "pendingAutoJoin": { "team@group.calendar.google.com": false } }
{ "name": "Local", "path": "~/Calendars/team.ics", "pendingAutoJoin": false }
```

## 設定

パネルの **設定** ボタン、または `omarchy-shell kaigi openSettings` で設定画面が開きます。
次のタブがあり、変更はその場で保存されます。

- **一般**: 自動参加（未返答の招待も開くかどうかはカレンダーごと）、会議の開き方、新しい会議を作るサービス、ブックマーク、フック
- **通知**: 開始と終了の通知とそれぞれのタイミング
- **カレンダー**: Google アカウント（追加・ログアウト）、アカウントごとに表示するカレンダー、アカウントごとの Chrome プロファイル、iCal フィード、表示する期間
- **表示**: バーの予定タイトル、残り時間、タイトルの文字数、進行中の会議の扱い、「近い予定だけ表示」、メニューのタイトル文字数と終了時刻
- **予定**: 終日の予定、会議リンクのない予定、参加者のいない予定、終わった予定、未返答・仮承諾・辞退した予定、非表示にした予定（元に戻す）
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
| `automaticEventJoin` / `…Time` | `false` / `0` | 開始の N 秒前に会議を開く。未返答や仮承諾の招待も対象。未返答の招待を一部のカレンダーだけ除くときは[未返答の招待の自動参加](#未返答の招待の自動参加)を参照。`showPendingEvents` / `showTentativeEvents` を `hide` にすると全カレンダーで除かれる（メニューからも消える） |
| `actionGraceSeconds` | `300` | スリープ明けなどで時刻を過ぎていても、この秒数以内なら実行する |
| `openMeetingsIn` | `browser` | `browser` は `xdg-open` で既定のブラウザに開く。`webapp` は `omarchy-launch-webapp` で、今いるワークスペースに単独のウィンドウとして開く（Chrome 系ブラウザのみ） |
| `providerOpeningModes` | `{}` | サービスごとの開き方。例: `{"zoom": "zoomApp", "teams": "teamsApp"}`。値は `default`（`openMeetingsIn` に従う）、`browser`、`webapp`、または下の「対応サービス」にあるアプリの指定。アプリが入っていなければブラウザで開く |
| `chromeProfile` | `""` | `webapp` のときに会議を開く Chrome のプロファイルのフォルダ名（`Default`、`Profile 2` など。`chrome://version` で確認できる）。空なら最後に使ったプロファイル。Google アカウントはログインしているプロファイルを自動で使うので、これは iCal カレンダーと、どのプロファイルにもログインしていないアカウント用。カレンダーごとにも指定できる。Google のカレンダーで指定した場合は、そのプロファイルにアカウントがログインしている間だけ使い、いなくなったら自動に戻る |
| `customRegexes` | `[]` | 追加の会議リンクのパターン。最後に試す |
| `filterEventRegexes` | `[]` | タイトルが一致した予定を隠す |
| `dismissedEvents` | `[]` | 「この予定を非表示」で非表示にした予定のID。通知と自動参加の対象からも外れる |
| `createMeetingService` | `meet` | パネルの「新しい会議」で開くサービス: `meet`、`zoom`、`teams`、`jitsi` |
| `bookmarks` | `[]` | パネルに並べる、よく使う会議のリンク: `["Daily https://meet.google.com/…", …]`（名前のあとにURL） |
| `eventHooks` | `false` | 会議の開始・終了時にフックを実行する（[フック](#フック)を参照） |


### フック

`eventHooks` をオンにすると、会議の開始時に `omarchy-hook kaigi-event-start`、終了時に `omarchy-hook kaigi-event-end` を実行します。
`~/.config/omarchy/hooks/kaigi-event-start` と `~/.config/omarchy/hooks/kaigi-event-end`（または `….d/` フォルダ）に実行可能なスクリプトを置いてください。
スクリプトは次の引数を受け取ります。

1. タイトル
2. 開始時刻（ISO 8601、UTC）
3. 終了時刻（ISO 8601、UTC）
4. 会議のリンク（なければ空）
5. カレンダー名

フックの対象は通知と同じです。辞退・キャンセル・終日・非表示にした予定は対象外で、同じ予定で二度は実行しません。

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

## マウス・キー・IPC

- **バー**: 左クリックでパネルを開く。中クリックで次の会議に参加する。右クリックでカレンダーを取り直す。
- **パネル**: 予定をクリックすると会議に参加します。予定の右端の ⌄ ボタン（会議リンクのない予定はクリックでも）で、場所・参加者・説明と「この予定を非表示」ボタンを表示します。「新しい会議」で、設定の「一般」で選んだサービスの会議を新しく作ります。Google Meet で Google アカウントを複数ログインしているときは、先にアカウントの一覧が出て、どのアカウントで作るかを選べます（参加するときと同じく Meet のリンクに `authuser` を付けます。`webapp` のときはそのアカウントの Chrome プロファイルでも開きます）。「ブックマーク」には登録した会議のリンクが並びます。
- **パネルのキー**: ↑/↓（または k/j）で予定を選び、→/← で詳細を開く・閉じる、Enter で参加する。`n` で次の会議に参加、`r` で更新、Esc で閉じる。Enter は予定を選んでいるときだけ効きます。
- **通知**: 開始の通知には「参加」と「5分後にもう一度通知」のボタンがあります。もう一度届いた通知にも同じボタンがあるので、また後にできます。
- **IPC**:
  - `omarchy-shell kaigi joinNext`（キーに割り当てると便利）
  - `omarchy-shell kaigi refresh`
  - `omarchy-shell kaigi next`
  - `omarchy-shell kaigi googleLogin`
  - `omarchy-shell kaigi openSettings`
  - `omarchy-shell kaigi createMeeting <meet|zoom|teams|jitsi>`（`""` なら設定で選んだサービス）。Meet でアカウントが複数あるときは、これまでどおりアカウントを指定せずに開く
  - `omarchy-shell kaigi createMeetingAs meet <メールアドレス>`（ログイン中のそのアカウントで Meet の会議を作る）
  - `omarchy-shell kaigi set <キー> <JSON>`
  - `omarchy-shell penguinwokrs.kaigi toggle`

## 仕組み

- `bin/kaigi_google.py` と `bin/kaigi-google` が Google へのログインと Calendar API を担当します。Python の標準ライブラリだけで動きます。
- `bin/kaigi-events` も標準ライブラリだけで動きます。フィードを読み、繰り返しの予定（RRULE、EXDATE、RDATE、RECURRENCE-ID、タイムゾーン、夏時間）を展開し、`bin/services.json` にある69種類のサービスのパターンで会議リンクを探します。会議アプリの URL スキーム（`zoommtg` など）が登録されているかも調べます。結果は JSON で出力します。
- `Service.qml` はシェルに1つだけ常駐します。1分ごとにヘルパーを呼び、5秒ごとに通知や自動参加の時刻を確認します。通知や参加の前に、その操作を `~/.local/state/kaigi/fired.json` に記録します。そのため、モニターが複数あっても、プラグインの再読み込みや `omarchy restart shell` をしても、同じ操作は繰り返されません。
- 開くのは、既知のサービス（または `customRegexes`）に一致した `https`、`http`、`zoommtg`、`discord` のURLと、そこから作った会議アプリ用のURL（`msteams`、`jitsi-meet`、`slack`、`riversidefm`、`tuple`、`workchat`）、それに同じスキームのブックマークと新しい会議のページだけです。URLはシェルを通さず、引数として渡します。
- `Panel.qml` がバーのウィジェットとパネル、`SettingsWindow.qml` が設定画面です。`Model.js` に予定の選び方、表示、タイミングの計算が入っています。

## 開発

プラグインのフォルダ内のファイルを保存すると、バーのウィジェットは自動で読み込み直されます。
`Service.qml` と `SettingsWindow.qml` の変更は、`omarchy restart shell` をするまで反映されません。

## テスト

```bash
python3 -m unittest discover -s tests
TZ=Asia/Tokyo node --test tests/
```

## プライバシー

[PRIVACY.md](PRIVACY.md) を参照してください。Kaigi はカレンダーを読み取るだけで、Google の API 以外にはどこにもデータを送りません。

## ライセンス

Apache-2.0 です。MeetingBar から取り入れた部分については `NOTICE` を参照してください。
