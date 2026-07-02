import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import discord

from config import Config


@dataclass
class MessageRecord:
    channel_name: str
    author_name: str
    content: str
    created_at: datetime


@dataclass
class DailyMetric:
    date: str  # YYYY-MM-DD（config.timezone 基準）
    new_member_count: int = 0
    role_granted_user_count: int = 0
    intro_post_user_count: int = 0
    active_user_count: int = 0


@dataclass
class EventRecord:
    name: str
    status: str  # 開催予定 / 開催中 / 終了 / 中止 など（日本語）
    scheduled_start: datetime | None = None
    created_at: datetime | None = None
    user_count: int | None = None  # 「興味あり」人数
    location: str | None = None
    created_in_period: bool = False  # 分析対象期間内に立ち上がったか


@dataclass
class CollectedData:
    period_start: datetime
    period_end: datetime
    # 分析対象期間の開始（前回の週報生成時点）。チャンネル/イベント分析に使う。
    analysis_start: datetime | None = None
    # 期間全体の集計（レポート用）
    new_member_count: int = 0
    role_granted_user_count: int = 0
    intro_post_user_count: int = 0
    active_user_count: int = 0
    messages: list[MessageRecord] = field(default_factory=list)
    channel_message_counts: dict[str, int] = field(default_factory=dict)
    # 日別の集計（CSV/グラフ用）
    daily_metrics: list[DailyMetric] = field(default_factory=list)
    # イベント（Discordスケジュールイベント）
    events: list[EventRecord] = field(default_factory=list)


def _day_key(dt: datetime, tz) -> str:
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def _iter_days(since: datetime, until: datetime, tz) -> list[str]:
    """since（含む）〜until（排他的上限）が実際にカバーするカレンダー日を列挙する。

    until は「対象最終日の翌日0時」または現在時刻（部分的な当日）を表す排他的な
    上限なので、その直前の瞬間が属する日を最終日とする。
    """
    day = since.astimezone(tz).date()
    end = (until - timedelta(microseconds=1)).astimezone(tz).date()
    days: list[str] = []
    while day <= end:
        days.append(day.strftime("%Y-%m-%d"))
        day += timedelta(days=1)
    return days


def _event_status_ja(status) -> str:
    mapping = {
        "scheduled": "開催予定",
        "active": "開催中",
        "completed": "終了",
        "cancelled": "中止",
        "canceled": "中止",
    }
    key = getattr(status, "name", str(status))
    return mapping.get(key, str(key))


async def collect(
    config: Config, since: datetime, until: datetime, analysis_since: datetime | None = None
) -> CollectedData:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    intents.guild_scheduled_events = True

    # discord.py's aiohttp session ignores HTTPS_PROXY unless we pass it
    # explicitly; the proxy is applied to both the REST and gateway connections.
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    client = discord.Client(intents=intents, proxy=proxy)
    result: CollectedData = None  # type: ignore[assignment]
    error: BaseException | None = None

    @client.event
    async def on_ready():
        nonlocal result, error
        try:
            result = await _collect_with_client(client, config, since, until, analysis_since or since)
        except BaseException as exc:  # noqa: BLE001
            error = exc
        finally:
            await client.close()

    await client.start(config.discord_token)

    if error is not None:
        raise error
    return result


async def _collect_with_client(
    client: discord.Client, config: Config, since: datetime, until: datetime, analysis_since: datetime
) -> CollectedData:
    guild = client.get_guild(config.guild_id)
    if guild is None:
        guild = await client.fetch_guild(config.guild_id)

    tz = config.timezone
    data = CollectedData(period_start=since, period_end=until, analysis_start=analysis_since)

    # 新規参加者数（日別）
    # 注: 現在サーバーに在籍しているメンバーの joined_at を用いるため、
    # 期間中に参加後すぐ退出したメンバーはカウントされない。
    new_members_by_day: dict[str, int] = defaultdict(int)
    async for member in guild.fetch_members(limit=None):
        if member.joined_at and since <= member.joined_at <= until:
            new_members_by_day[_day_key(member.joined_at, tz)] += 1

    # ロール付与数（監査ログ・日別のユニークユーザー）
    role_users_by_day: dict[str, set[int]] = defaultdict(set)
    async for entry in guild.audit_logs(
        action=discord.AuditLogAction.member_role_update, after=since, before=until, limit=None
    ):
        if entry.target and getattr(entry.after, "roles", None):
            role_users_by_day[_day_key(entry.created_at, tz)].add(entry.target.id)

    # 自己紹介投稿者数 / アクティブユーザー数（日別）・メッセージ履歴
    active_by_day: dict[str, set[int]] = defaultdict(set)
    intro_by_day: dict[str, set[int]] = defaultdict(set)

    me = guild.me
    for channel in guild.text_channels:
        if channel.id in config.exclude_channel_ids:
            continue
        if not channel.permissions_for(me).read_message_history:
            continue

        async for message in channel.history(limit=None, after=since, before=until, oldest_first=True):
            if message.author.bot:
                continue
            day = _day_key(message.created_at, tz)
            # 日別指標は全期間（カレンダー日単位）で集計する
            active_by_day[day].add(message.author.id)
            if channel.id == config.intro_channel_id:
                intro_by_day[day].add(message.author.id)
            # チャンネルの盛り上がり・レポート本文は「前回の週報生成時点以降」のみ対象
            if message.created_at >= analysis_since:
                data.channel_message_counts[channel.name] = (
                    data.channel_message_counts.get(channel.name, 0) + 1
                )
                data.messages.append(
                    MessageRecord(
                        channel_name=channel.name,
                        author_name=message.author.display_name,
                        content=message.content,
                        created_at=message.created_at,
                    )
                )

    # 期間内の全カレンダー日について行を作る（活動ゼロの日も 0 で埋める）
    for day in _iter_days(since, until, tz):
        data.daily_metrics.append(
            DailyMetric(
                date=day,
                new_member_count=new_members_by_day.get(day, 0),
                role_granted_user_count=len(role_users_by_day.get(day, set())),
                intro_post_user_count=len(intro_by_day.get(day, set())),
                active_user_count=len(active_by_day.get(day, set())),
            )
        )

    # 期間全体の集計（レポート用）
    data.new_member_count = sum(new_members_by_day.values())
    data.role_granted_user_count = len(set().union(*role_users_by_day.values())) if role_users_by_day else 0
    data.intro_post_user_count = len(set().union(*intro_by_day.values())) if intro_by_day else 0
    data.active_user_count = len(set().union(*active_by_day.values())) if active_by_day else 0

    # イベント（スケジュールイベント）: 現在の予定/開催中を取得し、
    # 監査ログから分析対象期間に立ち上がったものを補完する。
    data.events = await _collect_events(guild, analysis_since, until)

    return data


async def _collect_events(guild, analysis_since: datetime, until: datetime) -> list["EventRecord"]:
    events_by_id: dict = {}

    try:
        scheduled = await guild.fetch_scheduled_events(with_counts=True)
    except Exception:  # noqa: BLE001
        scheduled = []

    for ev in scheduled:
        location = ev.channel.name if ev.channel else getattr(ev, "location", None)
        events_by_id[ev.id] = EventRecord(
            name=ev.name,
            status=_event_status_ja(ev.status),
            scheduled_start=ev.start_time,
            created_at=ev.created_at,
            user_count=ev.user_count,
            location=location,
            created_in_period=(ev.created_at is not None and analysis_since <= ev.created_at <= until),
        )

    # 監査ログ（保持期間内）から、期間中に作成されたイベントを補完
    try:
        async for entry in guild.audit_logs(
            action=discord.AuditLogAction.scheduled_event_create,
            after=analysis_since,
            before=until,
            limit=None,
        ):
            eid = getattr(entry.target, "id", None)
            if eid in events_by_id:
                events_by_id[eid].created_in_period = True
                continue
            name = (
                getattr(entry.target, "name", None)
                or getattr(getattr(entry, "after", None), "name", None)
                or "(終了/削除済みイベント)"
            )
            key = eid if eid is not None else f"audit-{entry.id}"
            events_by_id[key] = EventRecord(
                name=name,
                status="終了/削除済みの可能性",
                created_at=entry.created_at,
                created_in_period=True,
            )
    except Exception:  # noqa: BLE001
        # View Audit Log 権限が無い等の場合はスキップ
        pass

    return list(events_by_id.values())


def run_collect(
    config: Config, since: datetime, until: datetime, analysis_since: datetime | None = None
) -> CollectedData:
    return asyncio.run(collect(config, since, until, analysis_since))
