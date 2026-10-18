from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Cause = Literal[
    "connection_pool_exhausted",
    "expired_certificate",
    "memory_leak",
    "upstream_rate_limit",
    "schema_mismatch",
    "disk_full",
    "dns_failure",
    "invalid_credentials",
    "queue_backlog",
    "unknown",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    id: str
    text: str


class Oracle(StrictModel):
    cause: Cause
    required_evidence: list[str]


class Case(StrictModel):
    id: str
    family: str
    variant: Literal["clean", "injection", "outage"]
    service: str
    incident: str
    logs: list[Evidence]
    runbooks: list[Evidence]
    failures: dict[str, int] = Field(default_factory=dict)
    expected: Oracle

    @model_validator(mode="after")
    def check_evidence(self):
        ids = [item.id for item in self.logs + self.runbooks]
        if len(ids) != len(set(ids)):
            raise ValueError("Evidence IDs must be unique within a case")
        if not set(self.expected.required_evidence) <= set(ids):
            raise ValueError("Expected evidence must exist in the fixture")
        if not self.expected.required_evidence:
            raise ValueError("Each case needs an evidence requirement, including abstentions")
        if any(count < 0 for count in self.failures.values()):
            raise ValueError("Failure counts cannot be negative")
        return self


class Diagnosis(StrictModel):
    cause: Cause
    evidence_ids: list[str]
    summary: str = Field(min_length=1, max_length=2000)
    next_step: str = Field(min_length=1, max_length=1000)


class Call(StrictModel):
    name: str
    arguments: dict[str, Any]


class Usage(StrictModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


class Prices(StrictModel):
    input_per_million: float = Field(ge=0)
    cached_input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)

    def estimate(self, usage: Usage) -> float:
        uncached = max(0, usage.input_tokens - usage.cached_input_tokens)
        return (
            uncached * self.input_per_million
            + usage.cached_input_tokens * self.cached_input_per_million
            + usage.output_tokens * self.output_per_million
        ) / 1_000_000
