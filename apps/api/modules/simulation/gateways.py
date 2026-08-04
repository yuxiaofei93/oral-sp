import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class PatientFact:
    code: str
    patient_expression: str
    certainty: str


@dataclass(frozen=True)
class GatewayResult:
    answer: str
    fact_codes: list[str]
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class PatientGateway:
    def answer(self, *, question: str, facts: list[PatientFact]) -> GatewayResult:
        raise NotImplementedError


class MockPatientGateway(PatientGateway):
    def answer(self, *, question: str, facts: list[PatientFact]) -> GatewayResult:
        del question
        started = time.monotonic()
        answer = " ".join(fact.patient_expression for fact in facts)
        return GatewayResult(
            answer=answer,
            fact_codes=[fact.code for fact in facts],
            provider="mock",
            model="deterministic-patient-v1",
            latency_ms=max(1, int((time.monotonic() - started) * 1000)),
        )


class OpenAICompatiblePatientGateway(PatientGateway):
    def __init__(self) -> None:
        self.base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        self.timeout_seconds = int(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
        if not self.base_url or not self.api_key or not self.model:
            raise GatewayError("外部模型尚未配置完整。")

    def answer(self, *, question: str, facts: list[PatientFact]) -> GatewayResult:
        started = time.monotonic()
        allowed_codes = [fact.code for fact in facts]
        fact_payload = [
            {
                "code": fact.code,
                "patient_expression": fact.patient_expression,
                "certainty": fact.certainty,
            }
            for fact in facts
        ]
        body = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你在口腔医学教学模拟中扮演患者。只能使用给定事实回答，使用第一人称，"
                        "一次只回答当前问题，不补充未定义信息，不提供诊断、检查结论或治疗建议。"
                        "返回 JSON：{\"answer\":\"患者回答\","
                        "\"fact_codes\":[\"使用的信息点编码\"]}。"
                        f"允许事实：{json.dumps(fact_payload, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": question},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_data = json.loads(response.read().decode("utf-8"))
            content = response_data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            answer = str(parsed["answer"]).strip()
            fact_codes = [str(code) for code in parsed.get("fact_codes", [])]
            if not answer or not fact_codes or not set(fact_codes).issubset(allowed_codes):
                raise GatewayError("模型返回了未授权事实或空回答。")
            usage = response_data.get("usage", {})
            return GatewayResult(
                answer=answer,
                fact_codes=fact_codes,
                provider="openai-compatible",
                model=self.model,
                latency_ms=max(1, int((time.monotonic() - started) * 1000)),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        except (urllib.error.URLError, TimeoutError, KeyError, TypeError, ValueError) as error:
            raise GatewayError("外部模型调用失败。") from error


def get_patient_gateway() -> PatientGateway:
    provider = os.environ.get("LLM_PROVIDER", "mock")
    if provider == "mock":
        return MockPatientGateway()
    if provider == "openai_compatible":
        return OpenAICompatiblePatientGateway()
    raise GatewayError(f"不支持的模型供应商配置：{provider}")


def request_hash(*, question: str, facts: list[PatientFact]) -> str:
    content = {
        "question": question,
        "facts": [
            {"code": fact.code, "expression": fact.patient_expression, "certainty": fact.certainty}
            for fact in facts
        ],
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
