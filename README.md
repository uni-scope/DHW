# Discord連携型 AIライター＆コミュニティ分析エージェント

Discordサーバーの活動データを収集し、Claude APIで日報（機能A）・note向け記事（機能B）を生成し、
指標の推移をCSV蓄積・グラフ化（機能C）するスクリプト群。

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

## 実行

```bash
python main.py                                   # 当日分を集計
python main.py --since 2026-06-04                # 6/4〜当日を日別に集計
python main.py --since 2026-06-04 --until 2026-06-30   # 期間指定
python main.py --since 2026-06-04 --skip-report  # 指標のみ（Claude API呼び出しなし）
```

集計期間は `config.timezone`（既定 Asia/Tokyo）のカレンダー日で解釈し、両端を含みます。
`--since`/`--until` を省略すると当日1日分を対象にします。

実行すると以下が生成されます。
- `reports/YYYY-MM-DD_daily.md`（管理者向けレポート。ファイル名は期間の最終日）
- `reports/YYYY-MM-DD_note.md`（note向け記事）
- `metrics_history.csv`（指標を**1日1行**で蓄積。同じ日付は上書き）
- `metrics_graph.png`（指標推移グラフ）

`metrics_history.csv` と `metrics_graph.png` はリポジトリで追跡し、実行のたびに更新・蓄積されます。

### 過去データのバックフィル

`--since` に過去日を指定すると、その日から当日までを1日ずつ集計し、CSV/グラフに日別の推移が作られます。

```bash
python main.py --since 2026-06-04 --until 2026-07-02
```

> **注意（集計の限界）**: 新規参加者数は「現在サーバーに在籍しているメンバーの参加日時」から算出するため、
> 期間中に参加後すぐ退出したメンバーは含まれません。また、ロール付与数はDiscordの監査ログ保持期間（約90日）内でのみ遡れます。

## 定期実行（GitHub Actions）

`.github/workflows/daily-report.yml` により、毎日 00:00 UTC（09:00 JST）に前日分を集計し、
`metrics_history.csv` と `metrics_graph.png` をリポジトリへコミットします。レポート（`reports/`）はワークフローのArtifactとして取得できます。

セットアップ:
1. リポジトリの **Secrets** に `DISCORD_TOKEN` と `ANTHROPIC_API_KEY` を登録
2. （任意）**Variables** に `GUILD_ID` / `INTRO_CHANNEL_ID` / `EXCLUDE_CHANNEL_IDS` を登録（未設定時はワークフロー内の既定値を使用）
3. ワークフローを**デフォルトブランチ**に置く（`schedule` トリガーはデフォルトブランチのワークフローのみ起動するため）

手動実行（`workflow_dispatch`）では `since`/`until`/`skip_report` を指定でき、バックフィルにも利用できます。

cron/タスクスケジューラで運用する場合は、日次で前日を指定して呼び出してください。

```bash
# 例: 毎日 09:05 JST に前日分を集計
5 9 * * * cd /path/to/repo && python main.py --since "$(date -d yesterday +\%F)" --until "$(date -d yesterday +\%F)"
```

## モデル使い分け

- 機能A（日報データ整形・要約）: Haiku（トークン抑制のため）
- 機能B（note記事執筆）: Sonnet
