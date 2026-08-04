import csv
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO

from django.utils import timezone

from .models import SessionAssessment, SessionStatus
from .reviews import latest_review, score_summary, unresolved_issues
from .scoring import generate_assessment

CENT = Decimal("0.01")
STATUS_LABELS = {
    "not_started": "未开始",
    SessionStatus.ACTIVE: "作答中",
    SessionStatus.COMPLETED: "已交卷",
    SessionStatus.EXPIRED: "已超时",
}


def _average(values: list[Decimal]) -> float | None:
    if not values:
        return None
    value = (sum(values, start=Decimal("0")) / len(values)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )
    return float(value)


def _session_report(session) -> dict:
    end_time = session.completed_at
    if session.status == SessionStatus.ACTIVE:
        end_time = min(timezone.now(), session.deadline_at)
    duration = max(0, int((end_time - session.started_at).total_seconds())) if end_time else None
    if session.status == SessionStatus.ACTIVE:
        return {
            "status": session.status,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "duration_seconds": duration,
            "score": None,
            "omissions": [],
            "errors": [],
            "review": None,
        }

    try:
        assessment = session.assessment
    except SessionAssessment.DoesNotExist:
        assessment = generate_assessment(session)
        session._prefetched_objects_cache.pop("score_results", None)
    review = latest_review(session)
    return {
        "status": session.status,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "duration_seconds": duration,
        "score": score_summary(session, review=review),
        "omissions": unresolved_issues(session, assessment.omissions, review=review),
        "errors": unresolved_issues(session, assessment.errors, review=review),
        "review": review,
    }


def assignment_report(assignment) -> dict:
    sessions = {
        session.student_id: session
        for session in assignment.sessions.select_related("assessment").prefetch_related(
            "score_results",
            "teacher_reviews__reviewer",
        )
    }
    rows = []
    for link in assignment.student_links.select_related("student").order_by(
        "student__display_name",
        "student__phone",
    ):
        session = sessions.get(link.student_id)
        report = _session_report(session) if session else None
        rows.append(
            {
                "student_id": str(link.student_id),
                "display_name": link.student.display_name,
                "phone": link.student.phone,
                "session_id": str(session.id) if session else None,
                "status": report["status"] if report else "not_started",
                "started_at": report["started_at"] if report else None,
                "completed_at": report["completed_at"] if report else None,
                "duration_seconds": report["duration_seconds"] if report else None,
                "score": report["score"] if report else None,
                "omissions": report["omissions"] if report else [],
                "errors": report["errors"] if report else [],
                "review_revision": (
                    report["review"].revision if report and report["review"] else None
                ),
                "teacher_comment": (
                    report["review"].comment if report and report["review"] else ""
                ),
            }
        )

    scored_rows = [row for row in rows if row["score"] is not None]
    completed_rows = [row for row in rows if row["status"] == SessionStatus.COMPLETED]
    ended_rows = [
        row
        for row in rows
        if row["status"] in (SessionStatus.COMPLETED, SessionStatus.EXPIRED)
    ]
    omission_counter = Counter(
        (item["code"], item["label"])
        for row in scored_rows
        for item in row["omissions"]
    )
    error_counter = Counter(
        (item["code"], item["label"])
        for row in scored_rows
        for item in row["errors"]
    )
    total_students = len(rows)
    scored_count = len(scored_rows)

    def common_items(counter):
        return [
            {
                "code": code,
                "label": label,
                "count": count,
                "rate": round(count * 100 / scored_count, 2) if scored_count else 0.0,
            }
            for (code, label), count in counter.most_common(10)
        ]

    score_values = [Decimal(str(row["score"]["final_score"])) for row in scored_rows]
    percentage_values = [
        Decimal(str(row["score"]["final_score"]))
        * Decimal("100")
        / Decimal(str(row["score"]["maximum_score"]))
        for row in scored_rows
        if row["score"]["maximum_score"] > 0
    ]
    duration_values = [
        Decimal(row["duration_seconds"])
        for row in ended_rows
        if row["duration_seconds"] is not None
    ]
    return {
        "summary": {
            "student_count": total_students,
            "started_count": sum(row["status"] != "not_started" for row in rows),
            "completed_count": len(completed_rows),
            "expired_count": sum(row["status"] == SessionStatus.EXPIRED for row in rows),
            "assessed_count": scored_count,
            "completion_rate": (
                round(len(completed_rows) * 100 / total_students, 2) if total_students else 0.0
            ),
            "average_score": _average(score_values),
            "average_score_percentage": _average(percentage_values),
            "average_duration_seconds": (
                round(float(sum(duration_values) / len(duration_values)))
                if duration_values
                else None
            ),
        },
        "frequent_omissions": common_items(omission_counter),
        "common_errors": common_items(error_counter),
        "rows": rows,
    }


def _safe_csv_cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _local_datetime(value) -> str:
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")


def assignment_csv(assignment, report: dict | None = None) -> str:
    report = report or assignment_report(assignment)
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            "学生姓名",
            "手机号",
            "作答状态",
            "开始时间",
            "结束时间",
            "用时（秒）",
            "自动得分",
            "当前得分",
            "已评分满分",
            "总满分",
            "仍有待评价项",
            "遗漏项",
            "错误项",
            "复核版本",
            "教师评语",
        ]
    )
    for row in report["rows"]:
        score = row["score"] or {}
        values = [
            row["display_name"],
            row["phone"],
            STATUS_LABELS[row["status"]],
            _local_datetime(row["started_at"]),
            _local_datetime(row["completed_at"]),
            row["duration_seconds"],
            score.get("automatic_score"),
            score.get("final_score"),
            score.get("scored_maximum"),
            score.get("maximum_score"),
            "是" if score.get("provisional") else ("否" if score else ""),
            "；".join(item["label"] for item in row["omissions"]),
            "；".join(item["label"] for item in row["errors"]),
            row["review_revision"],
            row["teacher_comment"],
        ]
        writer.writerow([_safe_csv_cell(value) for value in values])
    return "\ufeff" + buffer.getvalue()
