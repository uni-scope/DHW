from datetime import datetime

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


def append_metrics(config: Config, data: CollectedData, run_date: datetime) -> pd.DataFrame:
    row = {
        "date": run_date.strftime("%Y-%m-%d"),
        "new_member_count": data.new_member_count,
        "role_granted_user_count": data.role_granted_user_count,
        "intro_post_user_count": data.intro_post_user_count,
        "active_user_count": data.active_user_count,
    }

    try:
        history = pd.read_csv(config.metrics_csv_path)
    except FileNotFoundError:
        history = pd.DataFrame(columns=["date", *METRIC_COLUMNS])

    history = history[history["date"] != row["date"]]
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history = history.sort_values("date")
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
