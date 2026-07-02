import argparse
import json
import os
from datetime import date, datetime, time, timedelta

from anthropic import Anthropic

from collector import run_collect
from config import Config
from metrics import append_metrics, render_graph
from reporter import generate_note_article, generate_weekly_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discordの活動を集計し、週報・指標CSV・推移グラフを生成する。"
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="週報を生成する。対象期間は前回の週報生成時点（state）以降〜現在。",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="集計開始日（config.timezone 基準）。--weekly と併用すると前回時点の代わりに使う。",
    )
    parser.add_argument(
        "--until",
        metavar="YYYY-MM-DD",
        help="集計終了日（config.timezone 基準、両端含む）。省略時は現在。",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="レポート（Claude API呼び出し）をスキップし、指標のみ更新する。",
    )
    return parser.parse_args()


def _load_last_report_at(config: Config, tz) -> datetime | None:
    try:
        with open(config.state_path, encoding="utf-8") as f:
            raw = json.load(f).get("last_report_at")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def _save_last_report_at(config: Config, dt: datetime) -> None:
    with open(config.state_path, "w", encoding="utf-8") as f:
        json.dump({"last_report_at": dt.isoformat()}, f, ensure_ascii=False, indent=2)


def _resolve_period(config: Config, args: argparse.Namespace) -> tuple[datetime, datetime, datetime]:
    """(collect_since, until, analysis_since) を返す。

    - collect_since: 日別指標を完全なカレンダー日で取り直すための収集開始（0時に丸める）
    - analysis_since: チャンネル/イベント分析の起点（前回の週報生成時点）
    """
    tz = config.timezone
    now = datetime.now(tz)

    def _end_of(day: date) -> datetime:
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
        return min(end, now)

    if args.weekly:
        if args.since:
            analysis_since = datetime.combine(date.fromisoformat(args.since), time.min, tzinfo=tz)
        else:
            last = _load_last_report_at(config, tz)
            analysis_since = last if last is not None else now - timedelta(days=7)
        until = _end_of(date.fromisoformat(args.until)) if args.until else now
        # 分析起点の「その日の0時」から収集し、日別指標は完全日で上書きする
        collect_since = datetime.combine(analysis_since.astimezone(tz).date(), time.min, tzinfo=tz)
        return collect_since, until, analysis_since

    until_date = date.fromisoformat(args.until) if args.until else now.date()
    since_date = date.fromisoformat(args.since) if args.since else until_date
    if since_date > until_date:
        raise ValueError(f"--since ({since_date}) は --until ({until_date}) より後にできません。")
    since = datetime.combine(since_date, time.min, tzinfo=tz)
    return since, _end_of(until_date), since


def main() -> None:
    config = Config()
    args = _parse_args()
    tz = config.timezone
    since, until, analysis_since = _resolve_period(config, args)

    data = run_collect(config, since, until, analysis_since)

    history = append_metrics(config, data)
    render_graph(config, history)

    first_day = since.astimezone(tz).date()
    last_day = (until - timedelta(microseconds=1)).astimezone(tz).date()
    print(f"集計期間（指標）: {first_day} 〜 {last_day}")
    print(f"分析起点（チャンネル/イベント）: {analysis_since.astimezone(tz):%Y-%m-%d %H:%M}")
    print(f"指標CSVを更新しました: {config.metrics_csv_path}（{len(data.daily_metrics)}日分）")
    print(f"グラフを更新しました: {config.metrics_graph_path}")

    if args.skip_report:
        print("--skip-report が指定されたため、レポート生成をスキップしました。")
        return

    client = Anthropic(api_key=config.anthropic_api_key)
    weekly_report = generate_weekly_report(client, config, data, history)
    note_article = generate_note_article(client, config, data)

    os.makedirs(config.output_dir, exist_ok=True)
    date_str = last_day.strftime("%Y-%m-%d")

    weekly_path = os.path.join(config.output_dir, f"{date_str}_weekly.md")
    note_path = os.path.join(config.output_dir, f"{date_str}_note.md")

    with open(weekly_path, "w", encoding="utf-8") as f:
        f.write(weekly_report)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note_article)

    print(f"週報を出力しました: {weekly_path}")
    print(f"note記事を出力しました: {note_path}")

    # 週報を生成したら「前回生成時点」を更新する
    if args.weekly:
        _save_last_report_at(config, until)
        print(f"週報の生成時点を記録しました: {config.state_path}")


if __name__ == "__main__":
    main()
