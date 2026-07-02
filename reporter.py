from datetime import timedelta

from anthropic import Anthropic
from anthropic.types import Message

from collector import CollectedData
from config import Config

MAX_MESSAGES_IN_PROMPT = 800


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


def _channel_activity_block(data: CollectedData) -> str:
    ranked = sorted(data.channel_message_counts.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return "（メッセージなし）"
    return "\n".join(f"- #{name}: {count}件" for name, count in ranked)


def generate_daily_report(client: Anthropic, config: Config, data: CollectedData) -> str:
    period = _period_label(config, data)
    prompt = f"""あなたはDiscordコミュニティの運営アシスタントです。
以下の指標データとメッセージ履歴（対象期間: {period}）をもとに、管理者向けのレポートを作成してください。

# 指標データ（期間合計）
{_metrics_block(data)}

# チャンネル別メッセージ件数（全件ベース、多い順）
{_channel_activity_block(data)}

# メッセージ履歴
{_format_messages(config, data)}

# 出力要件
- 上記の指標データを表形式で記載する
- 「チャンネル別メッセージ件数」を根拠に、どのチャンネルが盛り上がっていたかを明記する
- 些末な雑談やつぶやきも含め、サーバー全体でどのようなトピックが話題になったかを簡潔にまとめる
- 気になる動き（急な話題の盛り上がり、トラブルの兆候など）があれば指摘する
- 全体で日本語、簡潔に（見出し＋箇条書き中心）"""

    message = client.messages.create(
        model=config.haiku_model,
        max_tokens=1500,
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
