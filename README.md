# 旅行記録（TRproject）

夫婦で旅行の計画・準備・思い出を一括管理するDjango製の個人用Webアプリ。
入力項目を増やしすぎず、必要なタイミングだけOpenAI APIを呼び出して
「旅のしおり」「旅のアルバム」生成を支援する。

公開URL（本番想定）: `https://household-app-bacon.net/travel/`

---

## 主な機能

| 機能 | 概要 |
|---|---|
| 旅行一覧 | キーワード / ステータス / 参加者で絞り込み可能。ステータスは開始日・終了日から自動算出 |
| 旅行新規作成 | 基本情報＋テーマ＋参加者＋（任意で）AIしおり一括生成 |
| 旅行詳細 | ログイン不要で閲覧可。未ログイン時は編集・削除・参加者欄を非表示。「🔗 URLコピー」バッジを常時表示 |
| 旅のしおり編集 | 基本情報、参加者、テーマ、Markdown旅行計画、Markdown準備リストを1画面で編集 |
| 旅のアルバム編集 | ベストショット、思い出メモ、旅行記本文を1画面で編集 |
| ビジュアル編集 | 旅行計画・準備リストはMarkdown直編集とビジュアル編集（カード/チェックリスト）をタブで切替 |
| 行程種別マスタ | 旅行計画の行程種別は `Kind` モデルで管理（絵文字＋ラベル＋表示順） |
| テーマ | `Theme` マスタへの多対多。一覧／詳細で絵文字バッジ列挙 |
| AIしおり一括生成 | 旅行計画(Markdown) / 準備リスト(Markdown) を生成・追記修正。フォームに直接反映し保存ボタンで確定 |
| AIアルバム支援 | 旅行記本文生成 / タイトル案 / 振り返り質問の3種をアルバム編集画面に集約 |
| AI履歴 | `AISuggestionLog` に呼び出し履歴を保存 |

---

## 技術スタック

- Python 3.11+ / Django 5.2
- フロントエンド: Djangoテンプレート + Bootstrap 5（スマホ優先）
- DB: PostgreSQL（本番はRaspberry Pi上）
- 画像: ImageField（`media/best_shots/` 配下に保存。DBにはパスのみ）
- AI: OpenAI API（既定モデル `gpt-5-nano`、`OPENAI_MODEL` で切替可）
- 本番デプロイ: Gunicorn + systemd + Nginx + Cloudflare Tunnel
- CI/CD: GitHub Actions self-hosted runner（main反映時に自動デプロイ）

主要パッケージは `requirements.txt` を参照。

---

## ディレクトリ構成（抜粋）

```
TRproject/
├── manage.py
├── requirements.txt
├── TRproject/        # Django設定（settings / urls / wsgi）
├── accounts/         # 認証・ユーザー（カスタムUser: email + username）
├── trips/            # 旅行記録メインアプリ
│   ├── models.py     # Trip / Kind / Theme / MemoryEntry / MemoryNote / AISuggestionLog
│   ├── views.py
│   ├── forms.py
│   ├── urls.py
│   ├── ai_service.py # OpenAI 呼び出し
│   └── templatetags/ # markdownify フィルタ
├── analytics/        # 簡易アクセス計測（is_staff のみ閲覧可）
├── templates/
├── static/
└── media/            # アップロードされたベストショット画像
```

---

## モデル概要

```
Trip
├── 基本: name / destination / start_date / end_date / summary / is_cancelled
├── status            : プロパティ（DB列ではなく日付から計算: preparing/ongoing/done/cancelled）
├── themes (M2M)      : Theme への多対多（最低1つ必須）
├── users  (M2M)      : 参加者
├── md_plan           : 旅行計画（Markdownテキスト）
├── md_packing        : 準備リスト（Markdown / GFMタスクリスト）
├── best_shot         : ベストショット画像（ImageField）
├── best_shot_caption : ベストショットの一言コメント
├── MemoryNote (多)   : 思い出の箇条書きメモ
├── MemoryEntry (1)   : journal / journal_generated_at（旅行記本文）
└── AISuggestionLog (多): AI呼び出し履歴

Kind   : 行程表の種別マスタ（emoji / label / order）
Theme  : 旅行テーマのマスタ（key / emoji / label / order）
```

準備リストはかつての `PackingItem` テーブルを廃止し、`Trip.md_packing` Markdownに統合済み（`## カテゴリ` 見出し + `- [ ] 項目名 — メモ` のGFMタスクリスト形式）。

---

## 認証・ユーザーポリシー

- 旅行詳細 `/trips/<pk>/` のみ匿名閲覧可。それ以外（一覧・新規・編集・削除・AI系）は要ログイン。
- 参加者選択候補は以下を除外：
  - `is_active=False`（無効化済みユーザー）
  - `is_superuser=True`（管理者）
  - `username` に「ゲスト」を含むユーザー（閲覧専用のゲストアカウント）

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

| URL | ビュー | 認証 | 用途 |
|---|---|---|---|
| `/trips/` | `trip_list` | 要ログイン | 旅行一覧（検索／ステータス／参加者で絞り込み） |
| `/trips/new/` | `trip_create` | 要ログイン | 新規作成（しおりフォーム＋AI一括生成） |
| `/trips/<pk>/` | `trip_detail` | **不要** | 詳細閲覧 |
| `/trips/<pk>/delete/` | `trip_delete` | 要ログイン | 削除確認 |
| `/trips/<pk>/shiori/edit/` | `shiori_edit` | 要ログイン | 旅のしおり編集（基本情報＋計画＋準備リスト） |
| `/trips/<pk>/album/edit/` | `album_edit` | 要ログイン | 旅のアルバム編集（ベストショット＋思い出＋旅行記） |
| `/trips/ai/shiori/` | `ai_shiori` | 要ログイン | AIしおり一括生成（新規作成画面用・pkなし） |
| `/trips/<pk>/ai/shiori/` | `ai_shiori` | 要ログイン | AIしおり一括生成（編集画面用・修正モード対応） |
| `/trips/<pk>/ai/questions/` | `ai_questions` | 要ログイン | AI: 振り返り質問（POST／JSON） |
| `/trips/<pk>/ai/journal/` | `ai_journal` | 要ログイン | AI: 旅行記本文生成（POST／JSON） |
| `/trips/<pk>/ai/titles/` | `ai_titles` | 要ログイン | AI: タイトル案（POST／JSON） |

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
- モデルは `.env` の `OPENAI_MODEL` で切り替え可能。既定 `gpt-5-nano`、本文品質が物足りなければ `gpt-5-mini` に切替を検討
- **旅のしおり編集 / 新規作成**: 「AIで入力」モーダルで生成対象（旅行計画 / 準備リスト）と自由テキストを指定。フォームに直接反映し、ユーザーが「保存」を押した時点で確定（DBには事前保存しない）。フォームに既存内容があるときは自動で「修正モード」となり、追加指示で示された箇所のみを差分上書きした完全版を返す
- **旅のアルバム編集**: 旅行記本文生成 / タイトル案 / 振り返り質問の3ボタンを配置
- **詳細(閲覧)画面**: AIボタンは置かない
- 旅行計画AIは `Kind` マスタの絵文字＋ラベルから種別を選ぶよう指示
- AI出力Markdownに `##` 日見出しが無い場合はサーバ側で `## 1日目` を自動補完。ビジュアルエディタ側でもテーブルのみのMarkdownを単一日として救済表示

---

## 本番デプロイ

Raspberry Pi 4上で `/travel/` パスとして公開する構成（Gunicorn + systemd + Nginx + Cloudflare Tunnel）。
GitHub Actions self-hosted runner により main 反映時に自動デプロイ。

`git pull` 後の手動更新手順:

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart trproject
```

詳細手順は仕様フォルダ `D:\Codespace\03_Notes\03_プロジェクト記録\Webアプリ\旅行記録\logs\deploy` を参照。

---

## 関連ドキュメント

- 現在仕様（正）: `D:\Codespace\03_Notes\03_プロジェクト記録\Webアプリ\旅行記録\000_AI_CONTEXT.md`
- 過去ログ・経緯: 同フォルダの `logs/` 配下
