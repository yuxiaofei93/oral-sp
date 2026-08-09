import json

from modules.simulation.ai_evaluation import OpenAICompatibleAIEvaluationGateway
from modules.simulation.gateways import (
    OpenAICompatiblePatientGateway,
    PatientFact,
    spoken_patient_fallback,
)


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def configure_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")


def test_spoken_fallback_answers_the_question_without_losing_fact_meaning():
    facts = [
        PatientFact(
            code="history.duration",
            patient_expression="牙龈疼痛病程约三年",
            certainty="certain",
        )
    ]

    assert spoken_patient_fallback(facts, question="疼了多久？") == "差不多有三年了。"
    assert (
        spoken_patient_fallback(facts, question="牙龈怎么不舒服？")
        == "我牙龈疼，差不多有三年了。"
    )


def test_deepseek_patient_gateway_disables_thinking_and_retries_empty_json(monkeypatch):
    configure_deepseek(monkeypatch)
    requests = []
    responses = iter(
        [
            JsonResponse(
                {
                    "model": "DeepSeek-V4-Flash-0731",
                    "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
                }
            ),
            JsonResponse(
                {
                    "model": "DeepSeek-V4-Flash-0731",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    '{"answer":"差不多有三年了。",'
                                    '"fact_codes":["history.duration"]}'
                                )
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 12},
                }
            ),
        ]
    )

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return next(responses)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = OpenAICompatiblePatientGateway(provider="deepseek").answer(
        question="疼了多久？",
        facts=[
            PatientFact(
                code="history.duration",
                patient_expression="差不多有三年了。",
                certainty="known",
            )
        ],
        history=[],
        patient_prompt="请表现得有些紧张，但回答要简短。",
    )

    assert len(requests) == 2
    request, timeout = requests[0]
    assert request.full_url == "https://api.deepseek.com/chat/completions"
    assert timeout == 12
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert "请表现得有些紧张，但回答要简短。" in body["messages"][0]["content"]
    assert "只能依据 allowed_facts 中提供的信息" in body["messages"][0]["content"]
    assert result.answer == "差不多有三年了。"
    assert result.model == "DeepSeek-V4-Flash-0731"
    assert result.input_tokens == 30
    assert result.output_tokens == 12


def test_deepseek_patient_gateway_routes_semantic_question_to_fact_code(monkeypatch):
    configure_deepseek(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return JsonResponse(
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                '{"fact_codes":["history.duration"],'
                                '"confidence":0.96}'
                            )
                        },
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 10},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = OpenAICompatiblePatientGateway(provider="deepseek").route(
        question="不舒服从什么时候开始的？",
        facts=[
            PatientFact(
                code="history.duration",
                standard_fact="病程约三年",
                patient_expression="差不多有三年了。",
                certainty="known",
            )
        ],
        history=[{"role": "patient", "content": "牙龈不舒服。"}],
    )

    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert "不舒服从什么时候开始的" in captured["body"]["messages"][1]["content"]
    assert "病程约三年" in captured["body"]["messages"][1]["content"]
    assert result.fact_codes == ["history.duration"]
    assert result.confidence == 0.96
    assert result.input_tokens == 80


def test_deepseek_router_recognizes_only_confident_physical_exam_requests(monkeypatch):
    configure_deepseek(monkeypatch)
    captured = []
    responses = iter(
        [
            '{"intent":"physical_exam_request","fact_codes":[],"confidence":0.91}',
            '{"intent":"physical_exam_request","fact_codes":[],"confidence":0.70}',
        ]
    )

    def fake_urlopen(request, timeout):
        del timeout
        captured.append(json.loads(request.data.decode("utf-8")))
        return JsonResponse(
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": next(responses)},
                    }
                ],
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    gateway = OpenAICompatiblePatientGateway(provider="deepseek")
    confident = gateway.route(
        question="可以让我检查一下您的口腔吗？",
        facts=[],
        history=[],
        physical_exam_available=True,
    )
    uncertain = gateway.route(
        question="是不是该看看？",
        facts=[],
        history=[],
        physical_exam_available=True,
    )

    assert confident.intent == "physical_exam_request"
    assert uncertain.intent == "patient_question"
    router_payload = json.loads(captured[0]["messages"][1]["content"])
    assert router_payload["physical_exam_available"] is True
    assert "findings_text" not in router_payload


def test_patient_gateway_retries_a_verbatim_written_fact_as_spoken_language(monkeypatch):
    configure_deepseek(monkeypatch)
    requests = []
    responses = iter(
        [
            JsonResponse(
                {
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    '{"answer":"嗯，牙龈疼痛病程约三年。",'
                                    '"fact_codes":["history.duration"]}'
                                )
                            },
                        }
                    ],
                }
            ),
            JsonResponse(
                {
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    '{"answer":"差不多有三年了。",'
                                    '"fact_codes":["history.duration"]}'
                                )
                            },
                        }
                    ],
                }
            ),
        ]
    )

    def fake_urlopen(request, timeout):
        del timeout
        requests.append(json.loads(request.data.decode("utf-8")))
        return next(responses)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = OpenAICompatiblePatientGateway(provider="deepseek").answer(
        question="疼了多久？",
        facts=[
            PatientFact(
                code="history.duration",
                patient_expression="牙龈疼痛病程约三年",
                certainty="certain",
            )
        ],
        history=[],
    )

    assert result.answer == "差不多有三年了。"
    assert len(requests) == 2
    assert "不要逐字复制" in requests[0]["messages"][0]["content"]
    assert any(
        "上一版回答仍在照抄" in message["content"]
        for message in requests[1]["messages"]
    )


def test_deepseek_ai_evaluation_uses_low_reasoning_effort(monkeypatch):
    configure_deepseek(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return JsonResponse(
            {
                "model": "DeepSeek-V4-Flash-0731",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"summary":"完成","items":[]}'},
                    }
                ],
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = OpenAICompatibleAIEvaluationGateway(provider="deepseek").evaluate(
        payload={"rubrics": [], "conversation": [], "submissions": []}
    )

    assert captured["body"]["thinking"] == {"type": "enabled"}
    assert captured["body"]["reasoning_effort"] == "low"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert result.model == "DeepSeek-V4-Flash-0731"
