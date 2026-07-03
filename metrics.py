import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd

from collector import CollectedData
from config import Config

METRIC_COLUMNS = [
    "new_member_count",
    "view_role_granted_count",
    "active_user_count",
]

# グラフ凡例（日本語）
METRIC_LABELS_JA = {
    "new_member_count": "新規参加者数",
    "view_role_granted_count": "DHUmember数",
    "active_user_count": "アクティブユーザー数",
}

# 各指標の定義（ダッシュボードの凡例ホバーで表示）。collector.py の集計ロジックに準拠。
METRIC_DEFS_JA = {
    "new_member_count": (
        "その日にサーバーへ新規参加したメンバー数。現在も在籍しているメンバーの参加日時を基に"
        "集計するため、期間中に参加後すぐ退出した人は含みません。"
    ),
    "view_role_granted_count": (
        "その日に「閲覧権限」ロールが付与されたユニークなユーザー数。"
        "自己紹介の投稿から「閲覧権限」ロールを自動付与しているため、"
        "実質的に新たにDHUmemberになった人数を表します。"
    ),
    "active_user_count": (
        "その日に対象テキストチャンネルのいずれかで1回以上発言したユニークなユーザー数"
        "（Bot・除外チャンネルを除く）。"
    ),
}

# 日本語表示に使えるフォント候補（先に見つかったものを使用）
_JP_FONT_CANDIDATES = [
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "IPAexGothic",
    "IPAGothic",
    "IPAPGothic",
    "TakaoGothic",
    "VL Gothic",
    "Yu Gothic",
    "Meiryo",
    "MS Gothic",
    "Hiragino Sans",
]


def _configure_japanese_font() -> None:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _JP_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    # マイナス記号が豆腐になるのを防ぐ
    plt.rcParams["axes.unicode_minus"] = False


def append_metrics(config: Config, data: CollectedData) -> pd.DataFrame:
    rows = [
        {
            "date": m.date,
            "new_member_count": m.new_member_count,
            "view_role_granted_count": m.view_role_granted_count,
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
    # スキーマを現在の指標カラムだけに正規化（旧カラムは破棄・欠損は0）
    for column in METRIC_COLUMNS:
        if column not in history.columns:
            history[column] = 0
    history = history[["date", *METRIC_COLUMNS]].fillna(0)
    for column in METRIC_COLUMNS:
        history[column] = history[column].astype(int)
    history = history.sort_values("date").reset_index(drop=True)
    history.to_csv(config.metrics_csv_path, index=False)
    return history


def render_graph(config: Config, history: pd.DataFrame) -> None:
    _configure_japanese_font()
    fig, ax = plt.subplots(figsize=(10, 6))
    dates = pd.to_datetime(history["date"])
    for column in METRIC_COLUMNS:
        series = history[column] if column in history.columns else 0
        ax.plot(dates, series, marker="o", label=METRIC_LABELS_JA[column])

    ax.set_title("コミュニティ指標の推移")
    ax.set_xlabel("日付")
    ax.set_ylabel("人数・件数")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(config.metrics_graph_path)
    plt.close(fig)
