# Discord連携型 AIライター＆コミュニティ分析エージェント

Discordサーバーの活動データを収集し、Claude APIで日報（機能A）・note向け記事（機能B）を生成し、
指標の推移をCSV蓄積・グラフ化（機能C）するスクリプト群。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env に DISCORD_TOKEN, ANTHROPIC_API_KEY, GUILD_ID,
# TARGET_CHANNEL_IDS, INTRO_CHANNEL_ID を設定
```

Discord Bot には以下のIntent/権限が必要です。
- Message Content Intent
- Server Members Intent
- View Audit Log 権限

## 実行

```bash
python main.py
```

実行すると以下が生成されます。
- `reports/YYYY-MM-DD_daily.md`（管理者向け日報）
- `reports/YYYY-MM-DD_note.md`（note向け記事）
- `metrics_history.csv`（指標の日次蓄積）
- `metrics_graph.png`（指標推移グラフ）

定期実行はcronやタスクスケジューラ等、環境側で `python main.py` を呼び出す形で行ってください。

## モデル使い分け

- 機能A（日報データ整形・要約）: Haiku（トークン抑制のため）
- 機能B（note記事執筆）: Sonnet
