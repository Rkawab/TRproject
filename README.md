# 旅行記録（TRproject）

夫婦で旅行の計画・準備・思い出を一括管理するDjango製の個人用Webアプリ。
シンプルなテキスト入力を中心に、必要なタイミングだけOpenAI APIを呼び出して
準備リスト・振り返り質問・旅行記本文の生成を支援する。

公開URL（本番想定）: `https://household-app-bacon.net/travel/`

---

## 主な機能

| 機能 | 概要 |
|---|---|
| 旅行一覧 | ステータス・キーワードで絞り込み可能な一覧画面 |
| 基本情報 | 旅行名・行き先・期間・テーマ・ステータス・概要メモ |
| 旅行計画（Markdown） | Markdownで自由に書ける計画欄。詳細ページでGitHub風プレビュー |
| ベストショット | 旅行ごとに**写真1枚 + 一言コメント**を残せる思い出機能 |
| 準備リスト | 持ち物 / 予約確認 / 事前購入 / 調べること / 出発前タスク |
| 思い出メモ | 箇条書きで自由に追加できる短文メモ（複数件） |
| 旅行記本文 | 思い出メモを踏まえてAIが旅行記本文を生成（手書きも可） |
| AI候補生成 | 準備リスト提案・振り返り質問・タイトル案 |

---

## 技術スタック

- Python 3.11+ / Django 5.2
- フロントエンド: Djangoテンプレート + Bootstrap 5（スマホ優先）
- DB: PostgreSQL（本番はRaspberry Pi上）
- 画像: ImageField（`media/best_shots/` 配下に保存。DBにはパスのみ）
- AI: OpenAI API（既定モデル `gpt-5-nano`）
- 本番デプロイ: Gunicorn + systemd + Nginx + Cloudflare Tunnel

主要パッケージは `requirements.txt` を参照。

---

## ディレクトリ構成（抜粋）

```
TRproject/
├── manage.py
├── requirements.txt
├── TRproject/        # Django設定（settings / urls / wsgi）
├── accounts/         # 認証・ユーザー
├── trips/            # 旅行記録メインアプリ
│   ├── models.py     # Trip / PackingItem / MemoryEntry / MemoryNote / AISuggestionLog
│   ├── views.py
│   ├── forms.py
│   ├── ai_service.py # OpenAI 呼び出し
│   └── templatetags/ # markdownify フィルタ
├── analytics/        # 簡易アクセス計測
├── templates/
├── static/
└── media/            # アップロードされたベストショット画像
```

---

## モデル概要

```
Trip
├── 基本: name / destination / start_date / end_date / theme / status / summary
├── md_plan          : 旅行計画（Markdownテキスト）
├── best_shot        : ベストショット画像（ImageField）
├── best_shot_caption: ベストショットの一言コメント
├── PackingItem (多)
├── MemoryNote  (多): 思い出の箇条書きメモ
├── MemoryEntry (1): journal / journal_generated_at（旅行記本文）
└── AISuggestionLog (多): AI呼び出し履歴
```

---

## ローカルセットアップ

```powershell
# 仮想環境
python -m venv ..\trenv
..\trenv\Scripts\Activate.ps1

# 依存関係
pip install -r requirements.txt

# .env を作成（プロジェクト直下）
# 例:
#   SECRET_KEY=...
#   DEBUG=True
#   dbname=travel_record
#   user=travel_user
#   password=...
#   host=localhost
#   port=5432
#   OPENAI_API_KEY=sk-...
#   OPENAI_MODEL=gpt-5-nano

# DB
python manage.py migrate
python manage.py createsuperuser

# 起動
python manage.py runserver
```

ブラウザで `http://127.0.0.1:8000/trips/` にアクセス。

---

## URL構成

| URL | ビュー | 用途 |
|---|---|---|
| `/trips/` | `trip_list` | 一覧 |
| `/trips/new/` | `trip_create` | 新規作成 |
| `/trips/<pk>/` | `trip_detail` | 詳細 |
| `/trips/<pk>/edit/` | `trip_edit` | 基本情報編集 |
| `/trips/<pk>/delete/` | `trip_delete` | 削除確認 |
| `/trips/<pk>/plan/edit/` | `trip_plan_edit` | 旅行計画（Markdown）編集 |
| `/trips/<pk>/best-shot/edit/` | `best_shot_edit` | ベストショット編集 |
| `/trips/<pk>/packing/edit/` | `packing_edit` | 準備リスト編集 |
| `/trips/<pk>/memory/edit/` | `memory_edit` | 思い出メモ・旅行記編集 |
| `/trips/<pk>/ai/packing/` | `ai_packing` | AI: 準備リスト提案（POST） |
| `/trips/<pk>/ai/questions/` | `ai_questions` | AI: 振り返り質問（POST） |
| `/trips/<pk>/ai/journal/` | `ai_journal` | AI: 旅行記生成（POST） |
| `/trips/<pk>/ai/titles/` | `ai_titles` | AI: タイトル案（POST） |

---

## 画像（ベストショット）の扱い

- `Trip.best_shot` は `ImageField`、`media/best_shots/` 配下に保存される
- DBに保存するのはパス文字列のみ（バイナリは保存しない）
- 開発時は `DEBUG=True` のとき `/media/...` をDjangoが配信
- 本番（Raspberry Pi）では `MEDIA_ROOT` を Nginx で配信する設定が必要

Nginx 設定例（本番）:

```nginx
location /travel/media/ {
    alias /opt/TRproject/media/;
}
```

---

## AI機能

- ボタンを押したときだけOpenAI APIを呼び出す方針（自動実行はしない）
- モデルは `.env` の `OPENAI_MODEL` で切り替え可能
- 既定 `gpt-5-nano` で運用し、本文品質が物足りなければ `gpt-5-mini` に切替

---

## 本番デプロイ

Raspberry Pi 4上で `/travel/` パスとして公開する構成。
詳細手順は Obsidian保管庫の以下ノートを参照。

- `03_Notes/03_プロジェクト記録/Webアプリ/旅行記録/logs/deploy/RaspberryPi駆動化_3アプリ目.md`

`git pull` 後の更新手順:

```bash
source venv/bin/activate
pip install -r requirements.txt   # Pillow を追加（ベストショット機能のため）
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart trproject
```

