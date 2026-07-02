import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from collector import CollectedData
from config import Config

METRIC_COLUMNS = [
    "new_member_count",
    "role_granted_user_count",
    "intro_post_user_count",
    "active_user_count",
]


def append_metrics(config: Config, data: CollectedData) -> pd.DataFrame:
    rows = [
        {
            "date": m.date,
            "new_member_count": m.new_member_count,
            "role_granted_user_count": m.role_granted_user_count,
            "intro_post_user_count": m.intro_post_user_count,
            "active_user_count": m.active_user_count,
        }
        for m in data.daily_metrics
    ]

    try:
        history = pd.read_csv(config.metrics_csv_path, dtype={"date": str})
    except FileNotFoundError:
        history = pd.DataFrame(columns=["date", *METRIC_COLUMNS])

    # 今回集計した日付は既存行を上書き（同日再実行でも重複しない）
    new_dates = {row["date"] for row in rows}
    history = history[~history["date"].isin(new_dates)]
    history = pd.concat([history, pd.DataFrame(rows)], ignore_index=True)
    history = history.sort_values("date").reset_index(drop=True)
    history.to_csv(config.metrics_csv_path, index=False)
    return history


def render_graph(config: Config, history: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    dates = pd.to_datetime(history["date"])
    for column in METRIC_COLUMNS:
        ax.plot(dates, history[column], marker="o", label=column)

    ax.set_title("Community Metrics Trend")
    ax.set_xlabel("Date")
    ax.set_ylabel("Count")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(config.metrics_graph_path)
    plt.close(fig)
