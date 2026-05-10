"""旅行記録 AI 連携サービス。

- 自動実行はせず、ビューからの明示的な呼び出しのみ
- モデル名は settings.OPENAI_MODEL（環境変数 OPENAI_MODEL）から取得
- 各呼び出しは AISuggestionLog に記録
"""
import json
import logging
import re

from django.conf import settings

from .models import AISuggestionLog, Trip

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
    theme_labels = [t.display for t in trip.themes.all()]
    if theme_labels:
        parts.append(f"テーマ: {'、'.join(theme_labels)}")
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


def _ensure_day_heading(md: str) -> str:
    """`##` 日見出しが1個も無いがテーブルが存在する場合、テーブル直前に `## 1日目` を補う。

    ビジュアルエディタ側のパーサも同様の救済を行うが、保存後のMarkdown正規性のため
    サーバ側でも自動補完しておく（日帰り計画でAIが `##` を省くケースの保険）。
    """
    if not md:
        return md
    lines = md.splitlines()
    has_day_heading = any(
        line.startswith("## ") and "🧠" not in line for line in lines
    )
    if has_day_heading:
        return md
    table_idx = -1
    for i, line in enumerate(lines):
        if re.match(r"^\|.*\|.*\|", line):
            table_idx = i
            break
    if table_idx < 0:
        return md
    insert = ["## 1日目", ""]
    # テーブル直前が空行で無ければ前に空行も足して整える
    if table_idx > 0 and lines[table_idx - 1].strip() != "":
        insert = ["", "## 1日目", ""]
    new_lines = lines[:table_idx] + insert + lines[table_idx:]
    logger.info("AI出力に `##` 日見出しが無かったため `## 1日目` を自動補完しました")
    return "\n".join(new_lines).rstrip() + "\n"


def _truncate_extra_day_sections(md: str, expected_day_count: int) -> str:
    """修正モードで AI が `##` 日見出しを増やしてきた場合、超過分を切り落とす。

    末尾の `## 🧠 ポイント` のような補足セクションは保持する。
    日見出し(🧠を含まない `## ` 行)の出現を数え、`expected_day_count` 個目を超えた箇所から
    次の「🧠 を含む `## `」または末尾までを除去する。
    """
    if expected_day_count <= 0:
        return md
    lines = md.splitlines()
    day_count = 0
    cut_start = -1
    for i, line in enumerate(lines):
        if line.startswith("## ") and "🧠" not in line:
            day_count += 1
            if day_count > expected_day_count:
                cut_start = i
                break
    if cut_start < 0:
        return md
    # 切り落とし区間の終点 = 末尾、または次の「🧠 を含む ##」(補足セクション)の直前
    cut_end = len(lines)
    for j in range(cut_start, len(lines)):
        if lines[j].startswith("## ") and "🧠" in lines[j]:
            cut_end = j
            break
    # 切り落とし直前の連続する `---` や空行も除去
    k = cut_start - 1
    while k >= 0 and (lines[k].strip() == "" or lines[k].strip() == "---"):
        k -= 1
    new_lines = lines[: k + 1] + (["", ""] if cut_end < len(lines) else []) + lines[cut_end:]
    truncated = "\n".join(new_lines).rstrip() + "\n"
    if cut_end > cut_start:
        logger.warning(
            "修正モードで余分な日セクションを %d 行切り落としました(expected=%d, got=%d)",
            cut_end - cut_start, expected_day_count, day_count,
        )
    return truncated


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
    "旅行計画の表は、ユーザーが書いた行動・時間配分を忠実に解釈し、"
    "各セルは短いフレーズ（説明文ではなく名詞句や『A → B』形式）で簡潔に書いてください。"
    "ユーザーが明示していない予定や時間を勝手に長く取らないでください。"
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
    kind_choices: list[str],
    trip: Trip | None = None,
    current_md_plan: str = "",
    current_md_packing: str = "",
) -> dict:
    """しおり編集／新規作成画面用に、旅行計画(md_plan)と準備リスト(md_packing)を一括生成する。

    targets に含めたキーのみ生成する（"plan" / "packing"）。

    `current_md_plan` / `current_md_packing` が非空かつ対応する target が選択されている場合は
    **修正モード** に切替。既存の Markdown をベースに、追加指示で必要な箇所だけ修正した完全版を返す。
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
        schema_parts.append('"md_packing": "Markdown形式の準備リスト全文"')
    schema = "{\n  " + ",\n  ".join(schema_parts) + "\n}"

    plan_refinement = bool(want_plan and current_md_plan and current_md_plan.strip())
    packing_refinement = bool(want_packing and current_md_packing and current_md_packing.strip())

    mode_note_parts = []
    if want_plan:
        mode_note_parts.append("旅行計画=" + ("修正" if plan_refinement else "新規生成"))
    if want_packing:
        mode_note_parts.append("準備リスト=" + ("修正" if packing_refinement else "新規生成"))

    prompt = f"""以下の旅行のしおり情報を生成してください。

旅行のメタ情報:
{meta_text}

ユーザーからの追加指示:
{instructions or '（特になし）'}

生成対象: {", ".join(targets)}
モード: {" / ".join(mode_note_parts)}
"""

    day_count = 0
    if plan_refinement:
        # 既存 md_plan の `## 見出し` 数を数えて、出力でも同数にすることを強制する
        existing_day_headings = [
            line for line in current_md_plan.strip().splitlines()
            if line.startswith("## ") and "🧠" not in line
        ]
        day_count = len(existing_day_headings)
        existing_headings_text = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(existing_day_headings))

        prompt += f"""
========================================
【⚠️⚠️⚠️ 旅行計画 修正モード — 既存の旅行計画を「その場で」直す ⚠️⚠️⚠️】

現在の旅行計画(これを **直接編集** する。新規生成ではない):
```
{current_md_plan.strip()}
```

既存の `##` 日見出し(全部で {day_count} 個):
{existing_headings_text or '  (なし)'}

【絶対に守る出力ルール】
1. **出力する `##` 日見出しの数は必ず {day_count} 個。それ以上でも以下でもない。**
2. **新しい `##` セクションを追加してはならない。**
   - ❌「補足」「追記」「Appendix」「予備」「準備編」のような追加 `##` セクションは絶対NG
   - ❌ 既存の日を分割して2つ以上の `##` にしない
   - ✅ 唯一の例外: 末尾に任意で `## 🧠 ポイント` セクションを置くのは可
3. ユーザーの追加指示が「○○を追加して」だった場合も、**該当する日のテーブルに行を1〜数行追加するだけ**で対応する。新しい `##` は作らない。
4. ユーザーの追加指示で **明示的に変更を求められた箇所だけ** を修正する。それ以外の行・時間・文言は **完全にそのまま保持** する。
5. 出力は差分ではなく **修正後の md_plan 完全な全文** を返す(全日分を再掲する)。
6. 元の各日のテーブル行数を大きく増やさない(指示で追加された分だけ)。
7. 構造ルール・種別マスタの制約(下記)は新規生成と同じく守る。

【自己チェック(出力前に確認)】
- 出力中の `##` 行を数えたか？ → {day_count} 個になっているか？
- 「補足」「追記」のような新セクションを作っていないか？
- 既存の行をむやみに書き換えていないか？

========================================
"""

    if want_plan:
        prompt += f"""
【旅行計画(md_plan)の構造ルール — 厳守】
- 先頭に全体タイトル: `# {{絵文字}} {{旅行名}} {{泊数 or 日帰り}}（{{日付範囲}}）行程表`
- そのあと **1日につき必ず `## 見出し` を1個だけ** 置く。複数日なら日数分の `##` を作る。日帰りなら `##` は1つだけ。
- 1日の **すべての時系列イベントは、その日の `##` の直下にある1つのテーブルにまとめて並べる**。イベントごとに `##` を切るのは絶対NG。
- 各日の見出し形式: `## {{絵文字}} {{M/D（曜日）}}｜{{当日の要約（10〜25文字程度）}}`
- 各日のテーブル形式（4列・**必ず1行以上のデータ行を入れる。空テーブル禁止**）:
  ```
  | 時間 | 内容 | 種別 | メモ |
  | --- | --- | --- | --- |
  | HH:MM–HH:MM | 内容 | <種別マスタの行をコピー> | メモ |
  ```
- 時間は `HH:MM–HH:MM`（en-dash「–」）または `HH:MM` 単独。
- 種別は **必ず下記「種別マスタ」の行を1つそのままコピーして使う**。絵文字とラベルを勝手に組み合わせない。マスタにない種別は **絶対に出力しない**。適切なものがマスタに無ければ空欄にする。
- 日と日の間は 空行 + `---` + 空行 で区切る（同じ日の中では絶対に `---` を入れない）。
- テーブル外には箇条書きや段落を書かない（末尾だけ任意で `## 🧠 ポイント` セクション可）。

【🚨 出力前の必須セルフチェック — 違反していたら書き直す】
- `## ` で始まる行（🧠 ポイントを除く）が **最低1個** あるか？
  - 日帰りでも `## 見出し` は **絶対に省略してはならない**。テーブルだけを置くのは禁止。
  - 該当する見出しが無い場合は、テーブルの直前に必ず日見出しを追加すること。

【書きぶり】
- 「内容」欄は **20文字以内の短いフレーズ**。名詞句や `A → B` 形式で書く。説明文は書かない。
  - ❌ `自宅から車で出発し、駅でメンバーと合流して目的地へ向かう`
  - ✅ `自宅 → 集合駅（合流）`
- 「メモ」欄は補足・固有名詞・注意点だけ。空でもよい。内容の言い換えは書かない。
- `**...**` 強調は1日あたり1〜3個の主要イベントのみ（移動・解散などは強調しない）。
- 行は必要なだけ細かく刻む。30分以上の停車・観光・食事は独立した行にする。

【ユーザー文の解釈ルール】
- 「○○で△△を拾う／合流」は **5〜10分の停車** として扱う。1時間以上滞在させない。
- 「SAで30分休憩」のように時間が明示されていればその時間を守る。
- 明示されていない時間を勝手に膨らませない（解散・追加観光等を盛らない）。
- 「持ち物」関連は準備リスト側で扱い、計画表には書かない。

【出力例（日帰り 1日の場合 — この**構造**を守る。種別欄の `<...>` は実出力では下記マスタの行をそのままコピーした実値に置き換える）】
```
# 🗻 サンプル日帰り観光（2026-XX-XX）行程表

## 🗻 X/X（X）｜日帰り登山＋温泉

| 時間 | 内容 | 種別 | メモ |
| --- | --- | --- | --- |
| 08:00–08:20 | 自宅 → ●●駅 | <種別マスタから選ぶ> | 車で移動 |
| 08:20–08:30 | 同行者ピックアップ | <種別マスタから選ぶ> | 駅前で合流 |
| 08:30–10:00 | ●●へ移動 | <種別マスタから選ぶ> |  |
| 10:00–11:00 | ●●休憩・食事 | <種別マスタから選ぶ> | SAで食事 |
| 11:00–12:00 | ●●へ移動 | <種別マスタから選ぶ> |  |
| 12:00–13:00 | **●●（約1時間）** | <種別マスタから選ぶ> | ●●必須 |
| 13:00–14:00 | ●●へ移動 | <種別マスタから選ぶ> |  |
| 14:00–14:30 | ●●で休憩 | <種別マスタから選ぶ> | タオル持参 |
| 14:30–16:00 | 自宅へ | <種別マスタから選ぶ> |  |
```

⚠️ 上記サンプルの種別欄 `<...>` プレースホルダは **実出力では絶対に使わない**。下記マスタの行(絵文字＋ラベル)をそのままコピーした実値、または空欄に置き換えること。

========================================
【種別マスタ — 種別欄にはこのリストのいずれかの行を**そのままコピー**して使う】
{kind_list}
========================================
"""

    if want_packing:
        if packing_refinement:
            prompt += f"""
========================================
【⚠️ 準備リスト 修正モード — 既存の準備リストをベースに直す ⚠️】

現在の準備リスト(これを **直接編集** する):
```
{current_md_packing.strip()}
```

【絶対に守る出力ルール】
1. ユーザーの追加指示で **明示的に変更を求められた箇所だけ** を修正する。それ以外のカテゴリ・項目・チェック状態(`- [ ]` / `- [x]`)は **完全にそのまま保持** する。
2. 出力は差分ではなく **修正後の md_packing 完全な全文** を返す。
3. 既存項目と重複する項目を新規追加してはならない。
4. ユーザーが「○○を追加して」と書いた場合は、最も適したカテゴリの末尾に `- [ ] {{項目名}}` を1〜数行追加するだけ。
5. ユーザーが「○○は不要」「○○を消して」と書いた場合は、その行を削除する。
6. 構造ルール(下記)は新規生成と同じく守る。

========================================
"""

        prompt += """
【準備リスト(md_packing)の構造ルール — 厳守】
- Markdown文字列で出力する。プレーンテキストとして見やすく、AIが追記しやすい構造にする。
- カテゴリごとに `## {絵文字} {ラベル}` の見出しを置く。標準のカテゴリは以下:
  - `## 🎒 持ち物`
  - `## ✅ 予約確認`
  - `## 🛒 事前購入`
  - `## 🔍 調べること`
  - `## 🏠 家を出る前にやること`
- 標準カテゴリ以外でも、旅行内容に合わせて自由にカテゴリを追加してよい(例: `## 📱 アプリ・連絡`)。ただし1カテゴリ1見出しで重複させない。
- 各見出しの下には GitHub Flavored Markdown の **タスクリスト形式** で項目を並べる:
  ```
  - [ ] パスポート
  - [x] 充電器 — 急速充電対応のもの
  ```
- 備考は項目名の後に ` — メモ`(半角スペース + em dash + 半角スペース + メモ)で続ける。短く1行で書く。なくてもよい。
- チェック状態は新規項目は基本 `- [ ]`(未完了)。既存項目は元の状態を保つ。
- 表(`|`)や引用(`>`)、コードブロックは使わない。シンプルなチェックリストのみ。
- 全体で20〜30項目程度を目安に、過不足なく必要なものに絞る。

【出力例】
```
## 🎒 持ち物
- [ ] パスポート
- [ ] 現金・クレジットカード
- [ ] 充電器 — 急速充電対応のもの

## ✅ 予約確認
- [ ] 航空券
- [ ] ホテル

## 🛒 事前購入
- [ ] 日焼け止め
```
"""

    prompt += f"\n出力JSON:\n{schema}\n"

    raw = _call_openai(prompt, SYSTEM_PROMPT, max_tokens=4000)
    if trip is not None:
        _log(trip, "shiori", prompt, raw)
    data = _parse_json(raw)

    result: dict = {}
    if want_plan:
        md = str(data.get("md_plan", "") or "").strip()
        # 修正モードなのに `##` 日見出しが増えていたら、超過分を切り捨てる(末尾の `## 🧠` 以外)
        if plan_refinement and md:
            md = _truncate_extra_day_sections(md, expected_day_count=day_count)
        # `##` が1個も無くテーブルだけのケースは、ビジュアルエディタが空表示になるので自動補完
        if md:
            md = _ensure_day_heading(md)
        result["md_plan"] = md
    if want_packing:
        md_pack = str(data.get("md_packing", "") or "").strip()
        if md_pack:
            md_pack = md_pack.rstrip() + "\n"
        result["md_packing"] = md_pack
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
