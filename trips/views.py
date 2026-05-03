from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# NOTE: 段階1ではモデル整備のみ。CRUD ビューは段階2で実装する。


@login_required
def trip_list(request):
    """旅行一覧（段階1: プレースホルダ）"""
    return render(request, "trips/list.html", {"trips": []})
