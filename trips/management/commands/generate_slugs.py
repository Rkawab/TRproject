"""既存の旅行レコードに AI スラグを生成・上書きするコマンド。

使い方:
  python manage.py generate_slugs          # slug が未設定 or フォールバック(trip-N) のものだけ対象
  python manage.py generate_slugs --force  # 全件対象（既存スラグも上書き）
"""
import re
import time

from django.core.management.base import BaseCommand

from trips.models import Trip


def _is_fallback_slug(slug: str) -> bool:
    return bool(re.fullmatch(r"trip-\d+", slug))


class Command(BaseCommand):
    help = "旅行タイトルから AI スラグを生成する"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="既存スラグも含めて全件再生成する",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="API呼び出し間の待機秒数（デフォルト 0.5 秒）",
        )

    def handle(self, *args, **options):
        from trips.ai_service import generate_slug

        force = options["force"]
        delay = options["delay"]

        if force:
            trips = Trip.objects.all()
        else:
            trips = [t for t in Trip.objects.all() if not t.slug or _is_fallback_slug(t.slug)]

        self.stdout.write(f"対象: {len(trips)} 件")

        for trip in trips:
            old_slug = trip.slug or "(なし)"
            try:
                base_slug = generate_slug(
                    trip.name,
                    destination=trip.destination or "",
                    start_date=trip.start_date,
                    fallback_pk=trip.pk,
                )
                # 重複回避
                slug = base_slug
                counter = 2
                while Trip.objects.filter(slug=slug).exclude(pk=trip.pk).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                trip.slug = slug
                trip.save(update_fields=["slug"])
                self.stdout.write(
                    self.style.SUCCESS(f"  [{trip.pk}] {trip.name}: {old_slug} → {slug}")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"  [{trip.pk}] {trip.name}: 失敗 ({e})")
                )
            if delay > 0:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("完了"))
