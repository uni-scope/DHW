# Discord連携型 AIライター＆コミュニティ分析エージェント

Discordサーバーの活動データを収集し、Claude APIで週報（管理者向け）・note向け記事を生成し、
指標の推移をCSV蓄積・グラフ化するスクリプト群。

週報は**オンデマンド（依頼時）**に生成し、以下を含みます。
- **ユーザー数の推移**（過去からの蓄積。週次集計＋推移グラフ）
- **チャンネルの盛り上がり**（前回の週報生成時点以降の書き込み数 上位3〜5チャンネルと要約）
- **イベントの立ち上がり・実施状況**（Discordスケジュールイベント）

> ボイスチャットの利用状況は対象外です。Discordには過去のVCセッションを返すAPIが無く、
> 取得するにはBotを常時起動して `voice_state_update` を記録し続ける必要があるためです。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env に DISCORD_TOKEN, ANTHROPIC_API_KEY を設定
# GUILD_ID / INTRO_CHANNEL_ID はデフォルトで設定済み
# 除外したいチャンネルがあれば EXCLUDE_CHANNEL_IDS に指定
```

集計対象チャンネルはBotが閲覧できる全テキストチャンネルを自動対象とします
（`EXCLUDE_CHANNEL_IDS` で指定したチャンネルのみ除外）。

Discord Bot には以下のIntent/権限が必要です。
- Message Content Intent
- Server Members Intent
- View Audit Log 権限

## 週報の生成（オンデマンド）

```bash
python main.py --weekly                 # 生成日から遡って1週間を集計して週報を生成
python main.py --weekly --skip-report   # 指標のみ更新（Claude API呼び出しなし）
python main.py --weekly --since 2026-06-25 --until 2026-07-02   # 期間を明示指定
```

`--weekly` は、**生成日から遡って1週間**（既定7日間）を対象にします。`--since`/`--until` で期間を明示指定もできます。

- 「ユーザー数の推移」は `metrics_history.csv` の**全履歴**（週次集計＋グラフ）を用います。
- 「チャンネルの盛り上がり」「イベント」は**対象期間（直近1週間）**を対象にします。

生成物:
- `reports/YYYY-MM-DD_weekly.md`（管理者向け週報。ファイル名は対象期間の最終日）
- `reports/YYYY-MM-DD_note.md`（note向け記事）
- `metrics_history.csv`（指標を**1日1行**で蓄積。同じ日付は上書き）
- `metrics_graph.png`（指標推移グラフ。**凡例・軸ラベルは日本語**）

`metrics_history.csv` / `metrics_graph.png` はリポジトリで追跡し、実行のたびに更新・蓄積されます。

> **グラフの日本語表示**: 日本語対応フォント（例: IPAGothic / Noto Sans CJK JP）が必要です。
> 見つからない場合は凡例が豆腐（□）になります。Ubuntu例: `sudo apt-get install -y fonts-ipafont-gothic`

### 指標だけのバックフィル

推移データを過去から埋めたい場合は、`--weekly` なしで期間を指定すると1日ずつ集計します。

```bash
python main.py --since 2026-06-04 --until 2026-07-02 --skip-report
```

> **注意（集計の限界）**: 新規参加者数は「現在サーバーに在籍しているメンバーの参加日時」から算出するため、
> 期間中に参加後すぐ退出したメンバーは含まれません。ロール付与数・イベントの立ち上がりはDiscordの監査ログ保持期間（約90日）内でのみ遡れます。
> ボイスチャットの履歴は取得できません（上記参照）。

## オンデマンド実行（GitHub Actions）

`.github/workflows/weekly-report.yml` は**手動実行（`workflow_dispatch`）専用**です（定期スケジュールはしません）。
実行すると週報を生成し、`metrics_history.csv` / `metrics_graph.png` / `weekly_state.json` をリポジトリへコミットし、
週報（`reports/`）をArtifactとして取得できます。

セットアップ:
1. リポジトリの **Secrets** に `DISCORD_TOKEN` と `ANTHROPIC_API_KEY` を登録
2. （任意）**Variables** に `GUILD_ID` / `INTRO_CHANNEL_ID` / `EXCLUDE_CHANNEL_IDS` を登録（未設定時はワークフロー内の既定値を使用）
3. Actions画面から「Weekly community report」を実行（`since`/`until`/`skip_report` を任意指定可）

## ダッシュボード（GitHub Pages）

`docs/` に常設ダッシュボード（`docs/index.html`）があり、実行のたびに `docs/data.json` が更新されます。
KPIタイル（前週比つき）・指標の推移グラフ（インタラクティブ／表ビュー切替）・チャンネルの盛り上がり
Top5・イベント一覧を表示し、「週報を生成」ボタンから GitHub Actions の実行画面へ遷移できます。

**プライバシー**: ダッシュボードは**集計値のみ**を表示します（メンバー名・発言内容は出しません）。
週報本文は Actions実行ページのサマリー／Artifact で限定閲覧してください。

### GitHub Pages の有効化

1. リポジトリの **Settings → Pages**
2. **Source** = 「Deploy from a branch」
3. **Branch** = `claude/beautiful-darwin-crqcwi`、フォルダ = **`/docs`** を選んで **Save**
4. 数分後、`https://<オーナー>.github.io/<リポジトリ>/` で公開されます

> GitHub Pages サイトは原則インターネット公開です（この構成は集計値のみ公開）。
> 週報本文を含む非公開運用が必要な場合は外部ホスティング＋認証が必要です。

グラフ描画には Chart.js を `docs/vendor/` に同梱しており、外部CDNに依存しません。

## モデル使い分け

- 週報（推移・チャンネル・イベントの分析）: Sonnet
- note記事執筆: Sonnet
