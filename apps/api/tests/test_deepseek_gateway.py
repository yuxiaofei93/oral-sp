import json

from modules.simulation.ai_evaluation import OpenAICompatibleAIEvaluationGateway
from modules.simulation.gateways import OpenAICompatiblePatientGateway, PatientFact


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
    assert result.answer == "差不多有三年了。"
    assert result.model == "DeepSeek-V4-Flash-0731"
    assert result.input_tokens == 30
    assert result.output_tokens == 12


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
