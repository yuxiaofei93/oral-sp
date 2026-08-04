from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import (
    CaseAssignment,
    ScoreDecision,
    ScoreResult,
    SessionStatus,
    SimulationSession,
    TeacherReview,
)
from .scoring import generate_assessment

CENT = Decimal("0.01")


class TeacherReviewError(Exception):
    code = "teacher_review_error"


class TeacherReviewFrozenError(TeacherReviewError):
    code = "teacher_review_frozen"


@dataclass(frozen=True)
class TeacherReviewResult:
    review: TeacherReview
    created: bool


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def latest_review(session: SimulationSession) -> TeacherReview | None:
    cached = getattr(session, "_prefetched_objects_cache", {}).get("teacher_reviews")
    if cached is not None:
        return max(cached, key=lambda item: item.revision, default=None)
    return session.teacher_reviews.select_related("reviewer").order_by("-revision").first()


def review_overrides(review: TeacherReview | None) -> dict[str, dict]:
    if review is None or not isinstance(review.score_overrides, dict):
        return {}
    return review.score_overrides


def effective_score(result: ScoreResult, review: TeacherReview | None) -> Decimal | None:
    override = review_overrides(review).get(result.code)
    if not isinstance(override, dict) or override.get("score") in (None, ""):
        return result.automatic_score
    return _money(override["score"])


def effective_decision(result: ScoreResult, review: TeacherReview | None) -> str:
    score = effective_score(result, review)
    if score is None:
        return ScoreDecision.PENDING
    if score <= 0:
        return ScoreDecision.MISSED
    if score >= result.max_score:
        return ScoreDecision.ACHIEVED
    return ScoreDecision.PARTIAL


def score_summary(
    session: SimulationSession,
    *,
    student_visible_only: bool = False,
    review: TeacherReview | None = None,
) -> dict:
    results = session.score_results.all()
    if student_visible_only:
        results = results.filter(is_student_visible=True)
    results = list(results)
    review = review if review is not None else latest_review(session)
    automatic_score = sum(
        (result.automatic_score for result in results if result.automatic_score is not None),
        start=Decimal("0.00"),
    )
    effective = [(result, effective_score(result, review)) for result in results]
    final_score = sum(
        (score for _, score in effective if score is not None),
        start=Decimal("0.00"),
    )
    scored_maximum = sum(
        (result.max_score for result, score in effective if score is not None),
        start=Decimal("0.00"),
    )
    maximum_score = sum(
        (result.max_score for result in results),
        start=Decimal("0.00"),
    )
    return {
        "automatic_score": float(_money(automatic_score)),
        "final_score": float(_money(final_score)),
        "scored_maximum": float(_money(scored_maximum)),
        "maximum_score": float(_money(maximum_score)),
        "provisional": any(score is None for _, score in effective),
    }


def unresolved_issues(
    session: SimulationSession,
    issues: list[dict],
    *,
    review: TeacherReview | None = None,
    student_visible_only: bool = False,
) -> list[dict]:
    results = session.score_results.all()
    if student_visible_only:
        results = results.filter(is_student_visible=True)
    result_by_code = {result.code: result for result in results}
    remaining = []
    for item in issues:
        result = result_by_code.get(item.get("code"))
        if result is None:
            remaining.append(item)
            continue
        score = effective_score(result, review)
        if score is None or score < result.max_score:
            remaining.append(item)
    return remaining


def create_teacher_review(
    *,
    session: SimulationSession,
    reviewer,
    comment: str,
    scores: list[dict],
) -> TeacherReviewResult:
    with transaction.atomic():
        assignment = CaseAssignment.objects.select_for_update().get(pk=session.assignment_id)
        locked = SimulationSession.objects.select_for_update().get(pk=session.pk)
        if locked.status == SessionStatus.ACTIVE:
            raise TeacherReviewError("学生仍在作答，暂不能复核成绩。")
        if assignment.feedback_released_at is not None:
            raise TeacherReviewFrozenError("反馈已发布，复核成绩已经冻结。")

        generate_assessment(locked)
        results = {result.code: result for result in locked.score_results.all()}
        previous = locked.teacher_reviews.order_by("-revision").first()
        normalized_overrides = dict(review_overrides(previous))
        seen_codes = set()
        for entry in scores:
            code = str(entry.get("code", "")).strip()
            if code in seen_codes:
                raise TeacherReviewError(f"评分项 {code} 重复提交。")
            seen_codes.add(code)
            result = results.get(code)
            if result is None:
                raise TeacherReviewError(f"评分项 {code} 不存在。")
            reason = str(entry.get("reason", "")).strip()
            if not reason:
                raise TeacherReviewError(f"调整“{result.label}”时必须填写理由。")
            value = entry.get("score")
            score = None if value in (None, "") else _money(value)
            if score is not None and (score < 0 or score > result.max_score):
                raise TeacherReviewError(
                    f"“{result.label}”的复核分数必须在 0 到 {result.max_score} 之间。"
                )
            normalized_overrides[code] = {
                "score": str(score) if score is not None else None,
                "reason": reason,
            }

        normalized_comment = comment.strip()
        if not normalized_comment and not normalized_overrides:
            raise TeacherReviewError("请至少填写教师评语或调整一个评分项。")

        if (
            previous
            and previous.comment == normalized_comment
            and previous.score_overrides == normalized_overrides
        ):
            return TeacherReviewResult(review=previous, created=False)

        effective = []
        for result in results.values():
            override = normalized_overrides.get(result.code)
            if override and override["score"] is not None:
                value = _money(override["score"])
            else:
                value = result.automatic_score
            effective.append((result, value))
        final_score = sum(
            (value for _, value in effective if value is not None),
            start=Decimal("0.00"),
        )
        scored_maximum = sum(
            (result.max_score for result, value in effective if value is not None),
            start=Decimal("0.00"),
        )
        maximum_score = sum(
            (result.max_score for result in results.values()),
            start=Decimal("0.00"),
        )
        review = TeacherReview.objects.create(
            session=locked,
            revision=(previous.revision + 1) if previous else 1,
            reviewer=reviewer,
            score_overrides=normalized_overrides,
            comment=normalized_comment,
            final_score=_money(final_score),
            scored_maximum=_money(scored_maximum),
            maximum_score=_money(maximum_score),
            provisional=any(value is None for _, value in effective),
        )
        return TeacherReviewResult(review=review, created=True)
