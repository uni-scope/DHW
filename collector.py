import asyncio
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
class CollectedData:
    period_start: datetime
    period_end: datetime
    new_member_count: int = 0
    role_granted_user_count: int = 0
    intro_post_user_count: int = 0
    active_user_count: int = 0
    messages: list[MessageRecord] = field(default_factory=list)
    channel_message_counts: dict[str, int] = field(default_factory=dict)


async def collect(config: Config) -> CollectedData:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    result: CollectedData = None  # type: ignore[assignment]
    error: BaseException | None = None

    @client.event
    async def on_ready():
        nonlocal result, error
        try:
            now = datetime.now(timezone.utc)
            since = now - timedelta(hours=24)
            result = await _collect_with_client(client, config, since, now)
        except BaseException as exc:  # noqa: BLE001
            error = exc
        finally:
            await client.close()

    await client.start(config.discord_token)

    if error is not None:
        raise error
    return result


async def _collect_with_client(
    client: discord.Client, config: Config, since: datetime, until: datetime
) -> CollectedData:
    guild = client.get_guild(config.guild_id)
    if guild is None:
        guild = await client.fetch_guild(config.guild_id)

    data = CollectedData(period_start=since, period_end=until)

    # 新規参加者数
    async for member in guild.fetch_members(limit=None):
        if member.joined_at and member.joined_at >= since:
            data.new_member_count += 1

    # ロール付与数（監査ログ）
    role_granted_users: set[int] = set()
    async for entry in guild.audit_logs(
        action=discord.AuditLogAction.member_role_update, after=since, before=until
    ):
        if getattr(entry.after, "roles", None):
            role_granted_users.add(entry.target.id)
    data.role_granted_user_count = len(role_granted_users)

    # 自己紹介チャンネル投稿者数・全チャンネルのアクティブユーザー数/メッセージ履歴
    active_users: set[int] = set()
    intro_users: set[int] = set()

    me = guild.me
    for channel in guild.text_channels:
        if channel.id in config.exclude_channel_ids:
            continue
        if not channel.permissions_for(me).read_message_history:
            continue

        async for message in channel.history(limit=None, after=since, before=until, oldest_first=True):
            if message.author.bot:
                continue
            active_users.add(message.author.id)
            data.channel_message_counts[channel.name] = data.channel_message_counts.get(channel.name, 0) + 1
            if channel.id == config.intro_channel_id:
                intro_users.add(message.author.id)
            data.messages.append(
                MessageRecord(
                    channel_name=channel.name,
                    author_name=message.author.display_name,
                    content=message.content,
                    created_at=message.created_at,
                )
            )

    data.active_user_count = len(active_users)
    data.intro_post_user_count = len(intro_users)

    return data


def run_collect(config: Config) -> CollectedData:
    return asyncio.run(collect(config))
