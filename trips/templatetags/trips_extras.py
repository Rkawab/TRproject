import markdown as md_lib
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="markdownify", is_safe=True)
def markdownify(value):
    """Markdown テキストを HTML に変換して返す（safe 済み）。"""
    if not value:
        return ""
    html = md_lib.markdown(
        value,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return mark_safe(html)
