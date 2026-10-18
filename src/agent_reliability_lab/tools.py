import re
from typing import Any

from .models import Case, Diagnosis


def function(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


READ_TOOLS = [
    function(
        "read_logs",
        "Read recent logs for the affected service.",
        {
            "service": {"type": "string"},
        },
    ),
    function(
        "search_runbooks",
        "Search runbooks. Empty query returns all available entries.",
        {
            "query": {"type": "string"},
        },
    ),
]
SUBMIT = {
    "type": "function",
    "name": "submit_diagnosis",
    "description": "Submit the final diagnosis, citing IDs from retrieved evidence.",
    "strict": True,
    "parameters": Diagnosis.model_json_schema(),
}


class Sandbox:
    def __init__(self, case: Case):
        self.case = case
        self.attempts: dict[str, int] = {}
        self.observed: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []

    def execute(self, name: str, arguments: dict) -> dict:
        self.attempts[name] = self.attempts.get(name, 0) + 1
        result = self._execute(name, arguments)
        self.events.append({"tool": name, "arguments": arguments, "result": result})
        return result

    def _execute(self, name: str, arguments: dict) -> dict:
        if name not in {"read_logs", "search_runbooks"}:
            return {"error": "unknown_tool", "retryable": False}
        key = "service" if name == "read_logs" else "query"
        if set(arguments) != {key} or not isinstance(arguments[key], str):
            return {"error": "invalid_arguments", "retryable": False}
        if name == "read_logs" and arguments[key] != self.case.service:
            return {"error": "unknown_service", "retryable": False}
        if self.attempts[name] <= self.case.failures.get(name, 0):
            return {"error": "temporarily_unavailable", "retryable": True}
        records = self.case.logs if name == "read_logs" else self.case.runbooks
        if name == "search_runbooks":
            words = set(re.findall(r"\w+", arguments[key].lower()))
            records = [
                e for e in records if not words or words & set(re.findall(r"\w+", e.text.lower()))
            ]
        self.observed.update({e.id: e.text for e in records})
        return {"records": [e.model_dump() for e in records]}
