import re

import markdown as md_lib
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


# GitHub Flavored Markdown のタスクリスト記法を絵文字に置換する。
# `markdown` パッケージは tasklist 拡張に標準対応していないため、
# 描画前に行頭の `- [ ]` / `- [x]` を `- ⬜` / `- ✅` に置き換えて視覚的に表現する。
_TASK_RE = re.compile(r"^(\s*[-*]\s+)\[([ xX])\](\s+)", re.MULTILINE)


def _replace_tasks(md: str) -> str:
    def repl(m):
        prefix, mark, suffix = m.group(1), m.group(2).lower(), m.group(3)
        icon = "✅" if mark == "x" else "⬜"
        return f"{prefix}{icon}{suffix}"
    return _TASK_RE.sub(repl, md)


@register.filter(name="markdownify", is_safe=True)
def markdownify(value):
    """Markdown テキストを HTML に変換して返す（safe 済み）。"""
    if not value:
        return ""
    html = md_lib.markdown(
        _replace_tasks(value),
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return mark_safe(html)
