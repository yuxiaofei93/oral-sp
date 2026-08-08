import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from modules.cases.models import (
    DiagnosisType,
    EvaluationMethod,
    ScoringDimension,
)

from .models import (
    ModelCall,
    ScoreDecision,
    ScoreResult,
    SessionAssessment,
    SimulationSession,
    StageSubmission,
    SubmissionType,
)

SCORING_VERSION = "rules-v1"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Evaluation:
    scoring_item: object | None
    code: str
    label: str
    dimension: str
    evaluation_method: str
    score: Decimal | None
    max_score: Decimal
    decision: str
    confidence: Decimal | None
    message_ids: list[str]
    submission_ids: list[str]
    evidence_excerpt: str
    standard_answer: str
    reason: str
    is_student_visible: bool
    source: str


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value).casefold(), flags=re.UNICODE)


def _contains(text: str, term: str) -> bool:
    normalized_term = _normalized(term)
    return bool(normalized_term) and normalized_term in _normalized(text)


def _submission_text(submission: StageSubmission | None) -> str:
    if submission is None:
        return ""

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    return "\n".join(strings(submission.payload))


def _decision(matched: int, total: int) -> str:
    if matched <= 0:
        return ScoreDecision.MISSED
    if matched >= total:
        return ScoreDecision.ACHIEVED
    return ScoreDecision.PARTIAL


def _ratio_score(max_score: Decimal, matched: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return _money(max_score * Decimal(matched) / Decimal(total))


def _pending(item, reason: str) -> Evaluation:
    return Evaluation(
        scoring_item=item,
        code=item.code,
        label=item.label,
        dimension=item.dimension,
        evaluation_method=item.evaluation_method,
        score=None,
        max_score=_money(item.max_score),
        decision=ScoreDecision.PENDING,
        confidence=None,
        message_ids=[],
        submission_ids=[],
        evidence_excerpt="",
        standard_answer="",
        reason=reason,
        is_student_visible=item.is_student_visible,
        source="pending",
    )


def _covered_facts(session):
    calls = (
        ModelCall.objects.filter(session=session, patient_message__isnull=False)
        .select_related("student_message", "patient_message")
        .order_by("created_at")
    )
    covered: dict[str, list[ModelCall]] = {}
    for call in calls:
        for code in call.matched_fact_codes:
            covered.setdefault(str(code), []).append(call)
    return covered


def _history_evaluation(item, session, config, covered_calls) -> Evaluation:
    requested_codes = [str(code) for code in config.get("fact_codes", [])]
    facts = list(session.case_version.facts.filter(code__in=requested_codes))
    if not requested_codes and session.case_version.facts.filter(code=item.code).exists():
        requested_codes = [item.code]
        facts = list(session.case_version.facts.filter(code=item.code))
    if not requested_codes or len(facts) != len(set(requested_codes)):
        return _pending(item, "病史评分项尚未配置有效的患者事实编码。")

    matched_facts = [fact for fact in facts if covered_calls.get(fact.code)]
    message_ids = []
    excerpts = []
    for fact in matched_facts:
        for call in covered_calls[fact.code]:
            message_ids.extend([str(call.student_message_id), str(call.patient_message_id)])
            excerpts.append(f"学生：{call.student_message.content}\n患者：{call.patient_message.content}")
    max_score = _money(item.max_score)
    return Evaluation(
        scoring_item=item,
        code=item.code,
        label=item.label,
        dimension=item.dimension,
        evaluation_method=item.evaluation_method,
        score=_ratio_score(max_score, len(matched_facts), len(facts)),
        max_score=max_score,
        decision=_decision(len(matched_facts), len(facts)),
        confidence=Decimal("1.0000"),
        message_ids=list(dict.fromkeys(message_ids)),
        submission_ids=[],
        evidence_excerpt="\n\n".join(excerpts)[:2000],
        standard_answer="；".join(fact.standard_fact for fact in facts),
        reason=f"覆盖 {len(matched_facts)}/{len(facts)} 个配置事实点。",
        is_student_visible=item.is_student_visible,
        source="history_facts",
    )


def _diagnosis_evaluation(item, session, config, submissions) -> Evaluation:
    diagnosis_names = [str(name) for name in config.get("diagnosis_names", [])]
    rules = session.case_version.diagnosis_rules.all()
    if diagnosis_names:
        rules = [rule for rule in rules if rule.name in diagnosis_names]
    elif item.dimension == ScoringDimension.DIFFERENTIAL:
        rules = [
            rule
            for rule in rules
            if rule.diagnosis_type in (DiagnosisType.INITIAL, DiagnosisType.DIFFERENTIAL)
            and rule.is_required
        ]
    elif item.dimension == ScoringDimension.FINAL_REASONING:
        rules = [
            rule
            for rule in rules
            if rule.diagnosis_type == DiagnosisType.FINAL and rule.is_required
        ]
    else:
        rules = []
    if not rules or (diagnosis_names and len(rules) != len(set(diagnosis_names))):
        return _pending(item, "诊断评分项尚未配置有效的标准诊断。")

    submission_type = (
        SubmissionType.FINAL_REASONING
        if item.dimension == ScoringDimension.FINAL_REASONING
        else SubmissionType.INITIAL_REASONING
    )
    submission = submissions.get(submission_type)
    text = _submission_text(submission)
    matched_rules = [
        rule
        for rule in rules
        if any(_contains(text, term) for term in [rule.name, *rule.aliases])
    ]
    max_score = _money(item.max_score)
    return Evaluation(
        scoring_item=item,
        code=item.code,
        label=item.label,
        dimension=item.dimension,
        evaluation_method=item.evaluation_method,
        score=_ratio_score(max_score, len(matched_rules), len(rules)),
        max_score=max_score,
        decision=_decision(len(matched_rules), len(rules)),
        confidence=Decimal("1.0000"),
        message_ids=[],
        submission_ids=[str(submission.id)] if submission else [],
        evidence_excerpt=text[:2000],
        standard_answer="；".join(rule.name for rule in rules),
        reason=f"命中 {len(matched_rules)}/{len(rules)} 个可接受诊断。",
        is_student_visible=item.is_student_visible,
        source="diagnoses",
    )


def _test_evaluation(item, session, config, submissions) -> Evaluation:
    test_codes = [str(code) for code in config.get("test_codes", [])]
    tests = session.case_version.tests.all()
    if test_codes:
        tests = [test for test in tests if test.code in test_codes]
    else:
        tests = [test for test in tests if test.requires_request]
    if not tests or (test_codes and len(tests) != len(set(test_codes))):
        return _pending(item, "检查评分项尚未配置有效的标准检查。")

    submission = submissions.get(SubmissionType.TEST_SELECTION)
    text = _submission_text(submission)
    matched_tests = [
        test
        for test in tests
        if _contains(text, test.name) or _contains(text, test.code)
    ]
    max_score = _money(item.max_score)
    return Evaluation(
        scoring_item=item,
        code=item.code,
        label=item.label,
        dimension=item.dimension,
        evaluation_method=item.evaluation_method,
        score=_ratio_score(max_score, len(matched_tests), len(tests)),
        max_score=max_score,
        decision=_decision(len(matched_tests), len(tests)),
        confidence=Decimal("1.0000"),
        message_ids=[],
        submission_ids=[str(submission.id)] if submission else [],
        evidence_excerpt=text[:2000],
        standard_answer="；".join(test.name for test in tests),
        reason=f"选择 {len(matched_tests)}/{len(tests)} 个配置检查项目。",
        is_student_visible=item.is_student_visible,
        source="tests",
    )


def _keyword_evaluation(item, config, submissions) -> Evaluation:
    keywords = [str(keyword) for keyword in config.get("keywords", []) if str(keyword).strip()]
    submission_type = str(config.get("submission_type", ""))
    if submission_type not in SubmissionType.values or not keywords:
        return _pending(item, "关键词评分项尚未配置提交阶段和关键词。")
    submission = submissions.get(submission_type)
    text = _submission_text(submission)
    matched = [keyword for keyword in keywords if _contains(text, keyword)]
    mode = config.get("match", "all")
    matched_count = len(keywords) if mode == "any" and matched else len(matched)
    max_score = _money(item.max_score)
    return Evaluation(
        scoring_item=item,
        code=item.code,
        label=item.label,
        dimension=item.dimension,
        evaluation_method=item.evaluation_method,
        score=_ratio_score(max_score, matched_count, len(keywords)),
        max_score=max_score,
        decision=_decision(matched_count, len(keywords)),
        confidence=Decimal("1.0000"),
        message_ids=[],
        submission_ids=[str(submission.id)] if submission else [],
        evidence_excerpt=text[:2000],
        standard_answer="；".join(keywords),
        reason=f"命中 {len(matched)}/{len(keywords)} 个配置关键词。",
        is_student_visible=item.is_student_visible,
        source="submission_keywords",
    )


def _evaluate_item(item, session, submissions, covered_calls) -> Evaluation:
    if item.evaluation_method != EvaluationMethod.RULE:
        label = "AI 辅助评价" if item.evaluation_method == EvaluationMethod.AI else "教师评价"
        return _pending(item, f"该评分项需要{label}，不计入当前自动得分。")
    config = item.matching_config or {}
    source = config.get("source")
    if source == "history_facts" or (not source and item.dimension == ScoringDimension.HISTORY):
        return _history_evaluation(item, session, config, covered_calls)
    if source == "diagnoses" or (
        not source
        and item.dimension in (ScoringDimension.DIFFERENTIAL, ScoringDimension.FINAL_REASONING)
    ):
        return _diagnosis_evaluation(item, session, config, submissions)
    if source == "tests" or (not source and item.dimension == ScoringDimension.TEST_PLAN):
        return _test_evaluation(item, session, config, submissions)
    if source == "submission_keywords":
        return _keyword_evaluation(item, config, submissions)
    return _pending(item, "该评分项没有可执行的规则配置。")


def _build_evaluations(session: SimulationSession) -> list[Evaluation]:
    submissions = {item.submission_type: item for item in session.submissions.all()}
    covered_calls = _covered_facts(session)
    scoring_items = list(session.case_version.scoring_items.all())
    return [
        _evaluate_item(item, session, submissions, covered_calls) for item in scoring_items
    ]


def _feedback_lists(evaluations: list[Evaluation]):
    omissions = []
    errors = []
    for item in evaluations:
        if not item.is_student_visible or item.decision not in (
            ScoreDecision.MISSED,
            ScoreDecision.PARTIAL,
        ):
            continue
        entry = {
            "code": item.code,
            "label": item.label,
            "reason": item.reason,
            "standard_answer": item.standard_answer,
        }
        omissions.append(entry)
        if item.source in ("diagnoses", "tests") and item.evidence_excerpt.strip():
            errors.append(
                {
                    **entry,
                    "reason": "学生提交内容未完整命中病例配置的可接受答案。",
                }
            )
    return omissions, errors


def generate_assessment(session: SimulationSession) -> SessionAssessment:
    existing = SessionAssessment.objects.filter(session=session).first()
    if existing:
        return existing

    evaluations = _build_evaluations(session)
    omissions, errors = _feedback_lists(evaluations)
    automatic_score = sum(
        (item.score for item in evaluations if item.score is not None),
        start=Decimal("0.00"),
    )
    scored_maximum = sum(
        (item.max_score for item in evaluations if item.score is not None),
        start=Decimal("0.00"),
    )
    maximum_score = sum(
        (item.max_score for item in evaluations),
        start=Decimal("0.00"),
    )
    pending_count = sum(item.decision == ScoreDecision.PENDING for item in evaluations)
    feedback_summary = (
        f"自动规则评分覆盖 {len(evaluations) - pending_count} 个评分项；"
        f"发现 {len(omissions)} 个遗漏项和 {len(errors)} 个需关注项。"
    )

    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().get(pk=session.pk)
        existing = SessionAssessment.objects.filter(session=locked).first()
        if existing:
            return existing
        ScoreResult.objects.bulk_create(
            [
                ScoreResult(
                    session=locked,
                    scoring_item=item.scoring_item,
                    code=item.code,
                    label=item.label,
                    dimension=item.dimension,
                    evaluation_method=item.evaluation_method,
                    automatic_score=item.score,
                    max_score=item.max_score,
                    decision=item.decision,
                    confidence=item.confidence,
                    evidence_message_ids=item.message_ids,
                    evidence_submission_ids=item.submission_ids,
                    evidence_excerpt=item.evidence_excerpt,
                    standard_answer=item.standard_answer,
                    reason=item.reason,
                    is_student_visible=item.is_student_visible,
                    rule_version=SCORING_VERSION,
                )
                for item in evaluations
            ]
        )
        return SessionAssessment.objects.create(
            session=locked,
            automatic_score=_money(automatic_score),
            scored_maximum=_money(scored_maximum),
            maximum_score=_money(maximum_score),
            provisional=bool(pending_count),
            omissions=omissions,
            errors=errors,
            feedback_summary=feedback_summary,
            scoring_version=SCORING_VERSION,
        )
