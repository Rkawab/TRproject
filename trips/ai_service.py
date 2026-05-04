"""旅行記録 AI 連携サービス。

- 自動実行はせず、ビューからの明示的な呼び出しのみ
- モデル名は settings.OPENAI_MODEL（環境変数 OPENAI_MODEL）から取得
- 各呼び出しは AISuggestionLog に記録
"""
import json
import logging

from django.conf import settings

from .models import AISuggestionLog, PACKING_CATEGORY_CHOICES, Trip

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    pass


def _get_client():
    from openai import OpenAI
    if not settings.OPENAI_API_KEY:
        raise AIServiceError("OPENAI_API_KEY が設定されていません（.env を確認）。")
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _call_openai(prompt: str, system: str, max_tokens: int = 1500) -> str:
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("OpenAI 呼び出し失敗: %s", e)
        raise AIServiceError(f"AI 呼び出しでエラーが発生しました: {e}")

    content = response.choices[0].message.content
    if not content:
        raise AIServiceError("AI から空の応答が返ってきました。")
    return content.strip()


def _parse_json(raw: str) -> dict:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("AI 応答の JSON パース失敗: %s", cleaned[:500])
        raise AIServiceError("AI 応答を JSON として解釈できませんでした。")


def _summarize_trip(trip: Trip) -> str:
    parts = [f"旅行名: {trip.name}"]
    if trip.destination:
        parts.append(f"行き先: {trip.destination}")
    if trip.start_date:
        parts.append(f"開始日: {trip.start_date:%Y-%m-%d}")
    if trip.end_date:
        parts.append(f"終了日: {trip.end_date:%Y-%m-%d}")
    if trip.duration_days:
        parts.append(f"日数: {trip.duration_days}日間")
    if trip.theme:
        parts.append(f"テーマ: {trip.theme}")
    if trip.summary:
        parts.append(f"概要: {trip.summary}")
    return "\n".join(parts)


def _summarize_packing(trip: Trip) -> str:
    items = list(trip.packing_items.all())
    if not items:
        return "（なし）"
    lines = [f"- [{i.get_category_display()}] {i.name}" for i in items]
    return "\n".join(lines)


def _summarize_memory_notes(trip: Trip) -> str:
    """MemoryNote（箇条書き思い出メモ）をまとめる。"""
    notes = list(trip.memory_notes.all())
    if not notes:
        return "（未記入）"
    lines = [f"- {note.body}" for note in notes]
    return "\n".join(lines)


def _log(trip: Trip, kind: str, prompt: str, response: str):
    AISuggestionLog.objects.create(
        trip=trip,
        kind=kind,
        model=settings.OPENAI_MODEL or "",
        prompt=prompt[:10000],
        response=response[:10000],
    )


SYSTEM_PROMPT = (
    "あなたは夫婦の旅行を一緒に整理するアシスタントです。"
    "出力は必ず指定された JSON 形式のみで、説明文を付けないでください。"
)


def suggest_packing(trip: Trip) -> list[dict]:
    """準備リストを AI に提案させる（既存項目との重複は避ける）。"""
    prompt = f"""以下の旅行に必要そうな準備リストを提案してください。

{_summarize_trip(trip)}

すでに登録済みの準備（重複しないように）:
{_summarize_packing(trip)}

カテゴリは次の英字コードを使ってください:
- belongings (持ち物)
- reservation (予約確認)
- purchase (事前購入)
- research (調べること)
- before_leaving (家を出る前にやること)

新しく必要そうな項目だけを最大 15 個まで返してください。
JSON:
{{
  "suggestions": [
    {{"category": "belongings", "name": "項目名", "note": "（任意・空でも可）"}}
  ]
}}
"""
    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=1500)
    _log(trip, "packing", prompt, raw)
    data = _parse_json(raw)

    valid_categories = {c[0] for c in PACKING_CATEGORY_CHOICES}
    cleaned = []
    for s in data.get("suggestions", []) or []:
        cat = s.get("category", "belongings")
        if cat not in valid_categories:
            cat = "belongings"
        name = str(s.get("name", "")).strip()
        if not name:
            continue
        cleaned.append({
            "category": cat,
            "name": name[:200],
            "note": str(s.get("note", "") or "")[:200],
        })
    return cleaned


def generate_questions(trip: Trip) -> list[str]:
    """思い出メモを元に、振り返り整理の質問を生成する。"""
    prompt = f"""旅行から戻ってきた夫婦が、思い出を振り返って整理するための質問を作ってください。
思い出メモを参考に、印象的だった出来事やまだ言葉にしていない気持ちを引き出すような質問を 5〜8 個。

{_summarize_trip(trip)}

記録した思い出メモ:
{_summarize_memory_notes(trip)}

JSON:
{{"questions": ["質問1", "質問2", "..."]}}
"""
    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=1000)
    _log(trip, "question", prompt, raw)
    data = _parse_json(raw)
    return [str(q) for q in (data.get("questions") or [])][:10]


def generate_journal(trip: Trip) -> str:
    """旅行記本文を生成する（夫婦のアルバム向けの温かみのある文章）。"""
    prompt = f"""夫婦の旅行アルバムに添える、思い出を振り返る旅行記の本文を書いてください。
温かみのある、読み返して楽しい文体で。800〜1500 文字程度。

{_summarize_trip(trip)}

思い出メモ:
{_summarize_memory_notes(trip)}

JSON:
{{"journal": "本文"}}
"""
    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=3000)
    _log(trip, "journal", prompt, raw)
    data = _parse_json(raw)
    return str(data.get("journal", "")).strip()


def suggest_titles(trip: Trip) -> list[str]:
    """旅行のタイトル候補を提案する。"""
    prompt = f"""この旅行の雰囲気にあったタイトル案を 5 つ提案してください。
短く、夫婦のアルバムに似合う親しみやすい雰囲気で。

{_summarize_trip(trip)}

思い出メモ:
{_summarize_memory_notes(trip)}

JSON:
{{"titles": ["案1", "案2", "案3", "案4", "案5"]}}
"""
    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=600)
    _log(trip, "title", prompt, raw)
    data = _parse_json(raw)
    return [str(t) for t in (data.get("titles") or [])][:10]
