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
    """OpenAI Chat Completions を呼ぶ。

    - gpt-5 系などの reasoning model は `max_tokens` 不可で `max_completion_tokens` 必須。
      かつ reasoning tokens も同じ上限を消費するため、上限を大きめに取り
      `reasoning_effort="minimal"` で推論コストを抑える。
    - 旧来のモデルは `max_tokens` にフォールバックする。
    """
    client = _get_client()
    model = settings.OPENAI_MODEL or ""
    is_reasoning = model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4")

    base_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    # reasoning モデルは推論トークンも上限に含まれるので大きく取る
    completion_limit = max(max_tokens * 4, 8000) if is_reasoning else max_tokens

    def _do_call(use_completion_param: bool, with_reasoning_effort: bool):
        kwargs = dict(base_kwargs)
        if use_completion_param:
            kwargs["max_completion_tokens"] = completion_limit
        else:
            kwargs["max_tokens"] = max_tokens
        if with_reasoning_effort:
            kwargs["reasoning_effort"] = "minimal"
        return client.chat.completions.create(**kwargs)

    try:
        try:
            response = _do_call(use_completion_param=True, with_reasoning_effort=is_reasoning)
        except Exception as inner:
            msg = str(inner).lower()
            if "reasoning_effort" in msg and "unsupported" in msg:
                # reasoning_effort 未サポートのモデルなら外して再試行
                response = _do_call(use_completion_param=True, with_reasoning_effort=False)
            elif "max_completion_tokens" in msg and "unsupported" in msg:
                # 旧モデル互換
                response = _do_call(use_completion_param=False, with_reasoning_effort=False)
            else:
                raise
    except Exception as e:
        logger.error("OpenAI 呼び出し失敗: %s", e)
        raise AIServiceError(f"AI 呼び出しでエラーが発生しました: {e}")

    choice = response.choices[0]
    content = choice.message.content
    if not content:
        # finish_reason などをログに残してデバッグしやすく
        finish_reason = getattr(choice, "finish_reason", None)
        usage = getattr(response, "usage", None)
        logger.error("AI から空応答: model=%s finish_reason=%s usage=%s", model, finish_reason, usage)
        if finish_reason == "length":
            raise AIServiceError(
                "AI の応答がトークン上限に到達して途切れました。"
                "指示文を短くするか、モデルを変更してください。"
            )
        raise AIServiceError(f"AI から空の応答が返ってきました（finish_reason={finish_reason}）。")
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


def generate_shiori(
    targets: list[str],
    instructions: str,
    trip_meta: dict,
    existing_packing_summary: str,
    kind_choices: list[str],
    trip: Trip | None = None,
) -> dict:
    """しおり編集／新規作成画面用に、旅行計画(md_plan)と準備リスト(packing)を一括生成する。

    targets に含めたキーのみ生成する（"plan" / "packing"）。
    """
    want_plan = "plan" in targets
    want_packing = "packing" in targets
    if not (want_plan or want_packing):
        raise AIServiceError("生成対象（旅行計画 / 準備リスト）が選択されていません。")

    label_map = {
        "name": "旅行名",
        "destination": "行き先",
        "start_date": "開始日",
        "end_date": "終了日",
        "duration_days": "日数",
        "theme": "テーマ",
        "summary": "概要",
    }
    meta_lines = []
    for key in ("name", "destination", "start_date", "end_date", "duration_days", "theme", "summary"):
        v = trip_meta.get(key)
        if v not in (None, ""):
            suffix = "日間" if key == "duration_days" else ""
            meta_lines.append(f"{label_map[key]}: {v}{suffix}")
    meta_text = "\n".join(meta_lines) or "（なし）"

    kind_list = "\n".join(f"- {k}" for k in kind_choices) or "（種別マスタ未登録）"

    schema_parts = []
    if want_plan:
        schema_parts.append('"md_plan": "Markdown形式の行程表全文"')
    if want_packing:
        schema_parts.append('"packing": [{"category": "...", "name": "...", "note": "（任意）"}]')
    schema = "{\n  " + ",\n  ".join(schema_parts) + "\n}"

    prompt = f"""以下の旅行のしおり情報を生成してください。

旅行のメタ情報:
{meta_text}

ユーザーからの追加指示:
{instructions or '（特になし）'}

すでに登録済みの準備リスト（重複しないように）:
{existing_packing_summary}

生成対象: {", ".join(targets)}
"""

    if want_plan:
        prompt += f"""
【旅行計画(md_plan)の出力ルール】
- 全体タイトル行: `# {{絵文字}} {{旅行名}} {{泊数}}（{{日付範囲}}）行程表` のような1行を先頭に置く
- 各日の見出し: `## {{絵文字}} {{M/D（曜日）}}｜{{要約}}` の形式（必ず `## ` から始める）
- 各日の内容は次のテーブルで記述する:
  `| 時間 | 内容 | 種別 | メモ |`
  `| --- | --- | --- | --- |`
- 時間は `HH:MM–HH:MM`（en-dash「–」を使用）または `HH:MM` 単独
- 強調したい項目は内容欄を `**...**` で囲む
- 種別欄は次の「種別マスタ」のいずれかを **そのまま** 入れる（絵文字＋ラベル）。マスタにない種別は使わない。種別不要なら空にする。
- 各日のテーブルの間は空行 + `---` + 空行 で区切る
- テーブル外には余計な箇条書きや段落を書かない（パーサー互換のため）
- 必要に応じて末尾にだけ `## 🧠 ポイント` のような補足セクションを置いてよい

種別マスタ:
{kind_list}
"""

    if want_packing:
        prompt += """
【準備リスト(packing)の出力ルール】
- カテゴリは次の英字コードのいずれかを使う:
  - belongings (持ち物)
  - reservation (予約確認)
  - purchase (事前購入)
  - research (調べること)
  - before_leaving (家を出る前にやること)
- 既存項目と重複しないように
- 新しく必要そうな項目だけ最大 20 件まで
"""

    prompt += f"\n出力JSON:\n{schema}\n"

    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=4000)
    if trip is not None:
        _log(trip, "shiori", prompt, raw)
    data = _parse_json(raw)

    result: dict = {}
    if want_plan:
        result["md_plan"] = str(data.get("md_plan", "") or "").strip()
    if want_packing:
        valid_categories = {c[0] for c in PACKING_CATEGORY_CHOICES}
        cleaned = []
        for s in data.get("packing", []) or []:
            cat = s.get("category", "belongings")
            if cat not in valid_categories:
                cat = "belongings"
            name = str(s.get("name", "") or "").strip()
            if not name:
                continue
            cleaned.append({
                "category": cat,
                "category_label": dict(PACKING_CATEGORY_CHOICES).get(cat, cat),
                "name": name[:200],
                "note": str(s.get("note", "") or "")[:200],
            })
        result["packing"] = cleaned
    return result


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
