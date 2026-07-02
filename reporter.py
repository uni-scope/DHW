from datetime import datetime, timedelta, timezone

import pandas as pd
from anthropic import Anthropic
from anthropic.types import Message

from collector import CollectedData
from config import Config
from metrics import METRIC_COLUMNS, METRIC_LABELS_JA

MAX_MESSAGES_IN_PROMPT = 800
TOP_CHANNELS = 5  # チャンネルの盛り上がり上位表示数（3〜5）


def _extract_text(message: Message) -> str:
    """Concatenate the text of all text blocks in the response.

    The response may include non-text blocks (e.g. thinking blocks) before the
    text, so we cannot assume ``content[0]`` is the answer.
    """
    parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()


def _period_bounds(config: Config, data: CollectedData) -> tuple:
    """対象期間の最初の日と最後の日（含む）を返す。

    period_end は排他的上限なので、直前の瞬間が属する日を最終日とする。
    """
    tz = config.timezone
    first = data.period_start.astimezone(tz).date()
    last = (data.period_end - timedelta(microseconds=1)).astimezone(tz).date()
    return first, last


def _period_label(config: Config, data: CollectedData) -> str:
    first, last = _period_bounds(config, data)
    if first == last:
        return first.strftime("%Y-%m-%d")
    return f"{first:%Y-%m-%d}〜{last:%Y-%m-%d}"


def _format_messages(config: Config, data: CollectedData) -> str:
    tz = config.timezone
    # 期間が複数日にまたがる場合は日付も表示する
    first, last = _period_bounds(config, data)
    multi_day = first != last
    fmt = "%m-%d %H:%M" if multi_day else "%H:%M"
    lines = []
    for msg in data.messages[:MAX_MESSAGES_IN_PROMPT]:
        ts = msg.created_at.astimezone(tz).strftime(fmt)
        lines.append(f"[{ts}] #{msg.channel_name} {msg.author_name}: {msg.content}")
    return "\n".join(lines)


def _metrics_block(data: CollectedData) -> str:
    return (
        f"- 新規参加者数: {data.new_member_count}\n"
        f"- ロール付与数: {data.role_granted_user_count}\n"
        f"- 自己紹介投稿者数: {data.intro_post_user_count}\n"
        f"- アクティブユーザー数（発言ユニークユーザー）: {data.active_user_count}"
    )


def _channel_top_block(data: CollectedData, top_n: int = TOP_CHANNELS) -> str:
    ranked = sorted(
        ((name, count) for name, count in data.channel_message_counts.items() if count > 0),
        key=lambda kv: kv[1],
        reverse=True,
    )[:top_n]
    if not ranked:
        return "（対象期間に書き込みはありませんでした）"
    return "\n".join(f"- #{name}: {count}件" for name, count in ranked)


def _weekly_trend_block(history: pd.DataFrame, weeks: int = 8) -> str:
    if history is None or history.empty:
        return "（推移データがまだありません）"
    df = history.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    iso = df["date"].dt.isocalendar()
    df["week"] = iso["year"].astype(str) + "-W" + iso["week"].astype(int).astype(str).str.zfill(2)
    agg = df.groupby("week")[METRIC_COLUMNS].sum().tail(weeks)

    header = "週 | " + " | ".join(METRIC_LABELS_JA[c] for c in METRIC_COLUMNS)
    rows = [header]
    for week, row in agg.iterrows():
        rows.append(f"{week} | " + " | ".join(str(int(row[c])) for c in METRIC_COLUMNS))
    return "\n".join(rows)


def _events_block(config: Config, data: CollectedData) -> str:
    if not data.events:
        return "（登録されているイベントはありません）"
    tz = config.timezone
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    lines = []
    for ev in sorted(data.events, key=lambda e: e.created_at or e.scheduled_start or epoch):
        parts = [f"- {ev.name}（状態: {ev.status}"]
        if ev.created_at:
            parts.append(f", 作成: {ev.created_at.astimezone(tz):%Y-%m-%d %H:%M}")
        if ev.scheduled_start:
            parts.append(f", 開催予定: {ev.scheduled_start.astimezone(tz):%Y-%m-%d %H:%M}")
        if ev.user_count is not None:
            parts.append(f", 興味あり: {ev.user_count}人")
        if ev.location:
            parts.append(f", 場所: {ev.location}")
        if ev.created_in_period:
            parts.append(", ★今回の対象期間に立ち上げ")
        parts.append("）")
        lines.append("".join(parts))
    return "\n".join(lines)


def generate_weekly_report(
    client: Anthropic, config: Config, data: CollectedData, history: pd.DataFrame
) -> str:
    period = _period_label(config, data)
    prompt = f"""あなたはDiscordコミュニティの運営アシスタントです。
以下のデータをもとに、管理者向けの「週報」をMarkdownで作成してください。
対象期間は前回の週報生成時点以降（{period}）です。

# 1. ユーザー数の推移（週次集計・直近）
{_weekly_trend_block(history)}

（参考）今回の対象期間の合計:
{_metrics_block(data)}

# 2. チャンネルの盛り上がり（対象期間の書き込み数・多い順）
{_channel_top_block(data)}

# 3. 登録イベント（立ち上がり・実施状況）
{_events_block(config, data)}

# 対象期間のメッセージ履歴（トピック要約の材料）
{_format_messages(config, data)}

# 出力要件（Markdown・日本語・見出し＋箇条書き中心）
## ユーザー数の推移
- 上記の週次集計をもとに、参加者数・アクティブ数などの増減トレンドを簡潔に述べる
## チャンネルの盛り上がり
- 書き込み数の多い上位3〜5チャンネルを挙げ、各チャンネルで何が話題だったかをメッセージ履歴を根拠に1〜2行で要約する
## イベント
- 上記「登録イベント」をもとに、対象期間に立ち上がったイベントと、各イベントの実施状況（開催予定/開催中/終了など）をまとめる
- 該当が無ければ「対象期間に新規イベントはありませんでした」とする

制約:
- 与えられたデータに無い数値・イベント・チャンネルを創作しないこと
- ボイスチャットについては本レポートの対象外"""

    message = client.messages.create(
        model=config.sonnet_model,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(message)


def generate_note_article(client: Anthropic, config: Config, data: CollectedData) -> str:
    period = _period_label(config, data)
    prompt = f"""あなたはコミュニティの様子を外部向けに発信するライターです。
以下のメッセージ履歴（対象期間: {period}）から、些末な雑談やノイズを除外し、
特定のイベント・トレンド・重要な気づきにフォーカスしたnote記事をMarkdown形式で書いてください。

# メッセージ履歴
{_format_messages(config, data)}

# 出力要件
- Markdown形式（タイトルは # 見出し）
- 外部の読者にも伝わるように、文脈や背景を補いながら書く
- 個人が特定されすぎないよう、必要に応じて表現を一般化してよい
- 雑談やノイズは取り上げず、記事になりうるトピックのみ扱う
- トピックが特になければ「対象期間中に特筆すべきイベントはありませんでした」と一言で終えてよい"""

    message = client.messages.create(
        model=config.sonnet_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(message)
