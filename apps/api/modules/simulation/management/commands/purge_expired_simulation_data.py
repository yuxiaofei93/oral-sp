from django.core.management.base import BaseCommand
from django.utils import timezone

from modules.simulation.retention import purge_expired_sessions, retention_preview


class Command(BaseCommand):
    help = "预览或清理超过保留期的模拟问诊数据；默认只预览。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="实际执行过期状态落库和数据删除；省略时只输出预览。",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        preview = retention_preview(now=now)
        self.stdout.write(f"检查时间：{now.isoformat()}")
        self.stdout.write(f"待落库的超时会话：{preview.stale_active_sessions}")
        self.stdout.write(f"可清理会话：{preview.deletable_sessions}")
        self.stdout.write(
            "关联记录："
            f"消息 {preview.messages}，病例记录 {preview.submissions}，"
            f"模型调用 {preview.model_calls}，评分项 {preview.score_results}，"
            f"教师复核 {preview.teacher_reviews}"
        )
        if not options["execute"]:
            self.stdout.write(self.style.WARNING("预览模式：未修改任何数据。"))
            self.stdout.write("确认范围后使用 --execute 执行清理。")
            return

        result = purge_expired_sessions(now=now)
        self.stdout.write(
            self.style.SUCCESS(
                f"已落库超时会话 {result.materialized_expirations} 个；"
                f"已删除会话 {result.deleted_sessions} 个、"
                f"关联记录 {result.deleted_related_records} 条。"
            )
        )
