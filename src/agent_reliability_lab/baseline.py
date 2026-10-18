from .models import Diagnosis
from .tools import Sandbox

SIGNATURES = {
    "POOL_WAIT_TIMEOUT": "connection_pool_exhausted",
    "CERT_HAS_EXPIRED": "expired_certificate",
    "HEAP_GROWTH_UNBOUNDED": "memory_leak",
    "UPSTREAM_429": "upstream_rate_limit",
    "UNDEFINED_COLUMN": "schema_mismatch",
    "ENOSPC": "disk_full",
    "DNS_NXDOMAIN": "dns_failure",
    "AUTH_TOKEN_REVOKED": "invalid_credentials",
    "CONSUMER_LAG_CRITICAL": "queue_backlog",
}


def diagnose(sandbox: Sandbox) -> Diagnosis:
    logs = sandbox.execute("read_logs", {"service": sandbox.case.service})
    sandbox.execute("search_runbooks", {"query": ""})
    matches = {
        cause
        for record in logs.get("records", [])
        for signature, cause in SIGNATURES.items()
        if signature in record["text"]
    }
    cause = matches.pop() if len(matches) == 1 else "unknown"
    return Diagnosis(
        cause=cause,
        evidence_ids=list(sandbox.observed),
        summary=f"Signature baseline result: {cause}.",
        next_step="Inspect service metrics and confirm the suspected failure before changing it.",
    )
