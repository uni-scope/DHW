import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


@dataclass
class Config:
    discord_token: str = field(default_factory=lambda: os.environ["DISCORD_TOKEN"])
    anthropic_api_key: str = field(default_factory=lambda: os.environ["ANTHROPIC_API_KEY"])
    guild_id: int = field(default_factory=lambda: int(os.environ["GUILD_ID"]))
    exclude_channel_ids: list[int] = field(
        default_factory=lambda: _split_ids(os.environ.get("EXCLUDE_CHANNEL_IDS", ""))
    )
    intro_channel_id: int = field(default_factory=lambda: int(os.environ["INTRO_CHANNEL_ID"]))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(os.environ.get("TIMEZONE", "Asia/Tokyo")))
    haiku_model: str = field(default_factory=lambda: os.environ.get("HAIKU_MODEL", "claude-haiku-4-5-20251001"))
    sonnet_model: str = field(default_factory=lambda: os.environ.get("SONNET_MODEL", "claude-sonnet-5"))
    output_dir: str = field(default_factory=lambda: os.environ.get("OUTPUT_DIR", "reports"))
    metrics_csv_path: str = field(default_factory=lambda: os.environ.get("METRICS_CSV_PATH", "metrics_history.csv"))
    metrics_graph_path: str = field(
        default_factory=lambda: os.environ.get("METRICS_GRAPH_PATH", "metrics_graph.png")
    )
    # 週報の「前回生成時点」を記録する状態ファイル
    state_path: str = field(default_factory=lambda: os.environ.get("STATE_PATH", "weekly_state.json"))
