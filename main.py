import argparse
import os
from datetime import date, datetime, time, timedelta

from anthropic import Anthropic

from collector import run_collect
from config import Config
from metrics import append_metrics, render_graph
from reporter import generate_daily_report, generate_note_article


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discordの活動を集計し、レポート・指標CSV・推移グラフを生成する。"
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="集計開始日（config.timezone 基準のカレンダー日、両端含む）。省略時は --until と同じ日。",
    )
    parser.add_argument(
        "--until",
        metavar="YYYY-MM-DD",
        help="集計終了日（config.timezone 基準のカレンダー日、両端含む）。省略時は当日。",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="日報・note記事（Claude API呼び出し）の生成をスキップし、指標のみ更新する。",
    )
    return parser.parse_args()


def _resolve_period(config: Config, args: argparse.Namespace) -> tuple[datetime, datetime]:
    tz = config.timezone
    today = datetime.now(tz).date()

    until_date = date.fromisoformat(args.until) if args.until else today
    since_date = date.fromisoformat(args.since) if args.since else until_date

    if since_date > until_date:
        raise ValueError(f"--since ({since_date}) は --until ({until_date}) より後にできません。")

    since = datetime.combine(since_date, time.min, tzinfo=tz)
    # until_date の終端（翌日0時）まで含める。ただし未来は現在時刻で打ち切る。
    until = datetime.combine(until_date + timedelta(days=1), time.min, tzinfo=tz)
    now = datetime.now(tz)
    if until > now:
        until = now
    return since, until


def main() -> None:
    config = Config()
    args = _parse_args()
    since, until = _resolve_period(config, args)

    data = run_collect(config, since, until)

    history = append_metrics(config, data)
    render_graph(config, history)

    tz = config.timezone
    first_day = since.astimezone(tz).date()
    last_day = (until - timedelta(microseconds=1)).astimezone(tz).date()
    print(f"集計期間: {first_day} 〜 {last_day}")
    print(f"指標CSVを更新しました: {config.metrics_csv_path}（{len(data.daily_metrics)}日分）")
    print(f"グラフを更新しました: {config.metrics_graph_path}")

    if args.skip_report:
        print("--skip-report が指定されたため、レポート生成をスキップしました。")
        return

    client = Anthropic(api_key=config.anthropic_api_key)
    daily_report = generate_daily_report(client, config, data)
    note_article = generate_note_article(client, config, data)

    os.makedirs(config.output_dir, exist_ok=True)
    date_str = until.astimezone(config.timezone).strftime("%Y-%m-%d")

    daily_path = os.path.join(config.output_dir, f"{date_str}_daily.md")
    note_path = os.path.join(config.output_dir, f"{date_str}_note.md")

    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_report)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note_article)

    print(f"日報を出力しました: {daily_path}")
    print(f"note記事を出力しました: {note_path}")


if __name__ == "__main__":
    main()
