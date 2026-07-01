from anthropic import Anthropic

from collector import CollectedData
from config import Config

MAX_MESSAGES_IN_PROMPT = 800


def _format_messages(data: CollectedData) -> str:
    lines = []
    for msg in data.messages[:MAX_MESSAGES_IN_PROMPT]:
        ts = msg.created_at.strftime("%H:%M")
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
    prompt = f"""あなたはDiscordコミュニティの運営アシスタントです。
以下の指標データとメッセージ履歴（過去24時間分）をもとに、管理者向けの日報を作成してください。

# 指標データ
{_metrics_block(data)}

# チャンネル別メッセージ件数（全件ベース、多い順）
{_channel_activity_block(data)}

# メッセージ履歴
{_format_messages(data)}

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
    return message.content[0].text


def generate_note_article(client: Anthropic, config: Config, data: CollectedData) -> str:
    prompt = f"""あなたはコミュニティの様子を外部向けに発信するライターです。
以下のメッセージ履歴（過去24時間分）から、些末な雑談やノイズを除外し、
特定のイベント・トレンド・重要な気づきにフォーカスしたnote記事をMarkdown形式で書いてください。

# メッセージ履歴
{_format_messages(data)}

# 出力要件
- Markdown形式（タイトルは # 見出し）
- 外部の読者にも伝わるように、文脈や背景を補いながら書く
- 個人が特定されすぎないよう、必要に応じて表現を一般化してよい
- 雑談やノイズは取り上げず、記事になりうるトピックのみ扱う
- トピックが特になければ「本日は特筆すべきイベントはありませんでした」と一言で終えてよい"""

    message = client.messages.create(
        model=config.sonnet_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
