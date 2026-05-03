from django.shortcuts import redirect


def home(request):
    """ルートURLへのアクセス: ログイン済みなら旅行一覧、未ログインならログイン画面へ"""
    if request.user.is_authenticated:
        return redirect("trips:list")
    return redirect("accounts:login")
