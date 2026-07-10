"""公開ダッシュボード用のデータ（docs/data.json）を書き出す。

個人情報は出さない: メンバー名・発言本文は含めず、集計値（指標の推移、
チャンネル別の件数、イベントの状態）のみをエクスポートする。
"""

import json
import os
from datetime import timedelta

import pandas as pd

from collector import CollectedData
from config import Config
from metrics import METRIC_COLUMNS, METRIC_DEFS_JA, METRIC_LABELS_JA

DOCS_DIR = "docs"
DATA_FILENAME = "data.json"
TOP_CHANNELS = 5
TOP_THREADS = 5


def _normalize_history(history: pd.DataFrame) -> pd.DataFrame:
    """現在の指標カラムだけに揃える（旧スキーマ／欠損に強くする）。"""
    df = history.copy()
    for col in METRIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0
    df = df[["date", *METRIC_COLUMNS]].fillna(0)
    for col in METRIC_COLUMNS:
        df[col] = df[col].astype(int)
    return df


def _kpis(history: pd.DataFrame, last_day) -> list[dict]:
    """直近7日（対象週）と、その前7日の合計を比較してKPIを作る。"""
    df = history.copy()
    df["date"] = pd.to_datetime(df["date"])
    end = pd.Timestamp(last_day)
    this_start = end - pd.Timedelta(days=6)
    prev_end = this_start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=6)

    this_mask = (df["date"] >= this_start) & (df["date"] <= end)
    prev_mask = (df["date"] >= prev_start) & (df["date"] <= prev_end)

    kpis = []
    for col in METRIC_COLUMNS:
        this_val = int(df.loc[this_mask, col].sum())
        prev_val = int(df.loc[prev_mask, col].sum())
        kpis.append(
            {
                "key": col,
                "label": METRIC_LABELS_JA[col],
                "value": this_val,
                "prev": prev_val,
                "delta": this_val - prev_val,
            }
        )
    return kpis


def write_dashboard_data(config: Config, data: CollectedData, history: pd.DataFrame) -> str:
    tz = config.timezone
    os.makedirs(DOCS_DIR, exist_ok=True)
    history = _normalize_history(history)

    first_day = data.period_start.astimezone(tz).date()
    last_day = (data.period_end - timedelta(microseconds=1)).astimezone(tz).date()

    repo = os.environ.get("GITHUB_REPOSITORY", "uni-scope/dhw")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    workflow_url = f"{server}/{repo}/actions/workflows/weekly-report.yml"
    actions_url = f"{server}/{repo}/actions"

    channels_top = sorted(
        ({"name": name, "count": count} for name, count in data.channel_message_counts.items() if count > 0),
        key=lambda c: c["count"],
        reverse=True,
    )[:TOP_CHANNELS]

    threads_top = sorted(
        (
            {"channel": channel, "name": thread, "count": count}
            for (channel, thread), count in data.thread_message_counts.items()
            if count > 0
        ),
        key=lambda t: t["count"],
        reverse=True,
    )[:TOP_THREADS]

    events = [
        {
            "name": ev.name,
            "status": ev.status,
            "scheduled_start": ev.scheduled_start.astimezone(tz).isoformat() if ev.scheduled_start else None,
            "user_count": ev.user_count,
            "created_in_period": ev.created_in_period,
        }
        for ev in data.events
    ]

    payload = {
        "generated_at": data.period_end.astimezone(tz).isoformat(),
        "period": {"start": first_day.isoformat(), "end": last_day.isoformat()},
        "repo": repo,
        "workflow_url": workflow_url,
        "actions_url": actions_url,
        "metric_columns": METRIC_COLUMNS,
        "metric_labels": METRIC_LABELS_JA,
        "metric_defs": METRIC_DEFS_JA,
        "kpis": _kpis(history, last_day),
        "history": history[["date", *METRIC_COLUMNS]].to_dict(orient="records"),
        "channels_top": channels_top,
        "threads_top": threads_top,
        "events": events,
        # 現在時点のスナップショット（総数）。「閲覧権限」ロールは DHUmember として表記する。
        "totals": {
            "member_count": data.total_member_count,
            "admin_role_count": data.admin_role_count,
            "dhumember_count": data.view_role_member_count,
            "view_role_name": config.view_role_name,
            "admin_role_name": config.admin_role_name,
        },
    }

    path = os.path.join(DOCS_DIR, DATA_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
