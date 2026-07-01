import os
from datetime import datetime

from anthropic import Anthropic

from collector import run_collect
from config import Config
from metrics import append_metrics, render_graph
from reporter import generate_daily_report, generate_note_article


def main() -> None:
    config = Config()
    run_date = datetime.now(config.timezone)

    data = run_collect(config)

    history = append_metrics(config, data, run_date)
    render_graph(config, history)

    client = Anthropic(api_key=config.anthropic_api_key)
    daily_report = generate_daily_report(client, config, data)
    note_article = generate_note_article(client, config, data)

    os.makedirs(config.output_dir, exist_ok=True)
    date_str = run_date.strftime("%Y-%m-%d")

    daily_path = os.path.join(config.output_dir, f"{date_str}_daily.md")
    note_path = os.path.join(config.output_dir, f"{date_str}_note.md")

    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(daily_report)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note_article)

    print(f"日報を出力しました: {daily_path}")
    print(f"note記事を出力しました: {note_path}")
    print(f"指標CSVを更新しました: {config.metrics_csv_path}")
    print(f"グラフを更新しました: {config.metrics_graph_path}")


if __name__ == "__main__":
    main()
