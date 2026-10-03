"""
orchestrator_core/exceptions.py

All custom exceptions for the v2 FastAPI service.
Centralised here so they can be imported without pulling in any agent or storage code.
"""


class ApprovalGateError(Exception):
    """Base exception for all approval gate and security violations."""
    pass


class ApprovalNotFoundError(ApprovalGateError):
    """Raised when execute_approved() is called with an id that has no DB row."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval record not found: {approval_id}")


class ApprovalNotGrantedError(ApprovalGateError):
    """Raised when execute_approved() is called on a record whose status is not 'approved'."""
    def __init__(self, approval_id: str, status: str):
        self.approval_id = approval_id
        self.status = status
        super().__init__(f"Approval {approval_id} is in state '{status}', expected 'approved'")


class ApprovalExpiredError(ApprovalGateError):
    """Raised when execute_approved() is called on a record that has passed its expires_at."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval {approval_id} has expired and can no longer be executed")


class ApprovalAlreadyExecutedError(ApprovalGateError):
    """Raised when execute_approved() is called on a record that is already in 'executed' state."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval {approval_id} was already executed — cannot execute twice")


class ApprovalClaimConflictError(ApprovalGateError):
    """Raised when the compare-and-set claim for 'executing' state fails (concurrent call won)."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Another process already claimed execution of approval {approval_id}")


class ApprovalHashMismatchError(ApprovalGateError):
    """Raised when expected_hash provided during approval does not match payload_hash (TOCTOU violation)."""
    def __init__(self, approval_id: str, expected_hash: str, actual_hash: str):
        self.approval_id = approval_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Approval {approval_id} hash mismatch (TOCTOU violation): expected '{expected_hash}', but actual is '{actual_hash}'"
        )


class ApprovalTamperedError(ApprovalGateError):
    """Raised when canonical payload hash does not match stored payload_hash at execution time (SEC-02)."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(
            f"Approval {approval_id} payload or action_type has been tampered with; hash verification failed"
        )


class ApprovalSignatureInvalidError(ApprovalGateError):
    """Raised when HMAC signature verification fails (unauthorized state transition or DB tampering, SEC-03)."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(
            f"Approval {approval_id} has an invalid or forged HMAC approval signature; execution refused"
        )


class ApprovalSupersededError(ApprovalGateError):
    """Raised when attempting to execute or approve an approval that has been superseded by a newer version (SEC-06)."""
    def __init__(self, approval_id: str, supersedes_id: str | None = None):
        self.approval_id = approval_id
        self.supersedes_id = supersedes_id
        super().__init__(
            f"Approval {approval_id} has been superseded by a newer version and cannot be executed"
        )


class IdempotencyConflictError(ApprovalGateError):
    """Raised when an action with the same idempotency_key has already been executed (SEC-04)."""
    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(
            f"An action with idempotency key '{idempotency_key}' has already been executed"
        )


class SecurityPolicyViolationError(ApprovalGateError):
    """Raised when a proposed target or recipient violates security policy (SEC-08)."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Security policy violation: {reason}")


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is in open state — too many consecutive LLM failures."""
    def __init__(self, service: str, cooldown_remaining_s: float):
        self.service = service
        self.cooldown_remaining_s = cooldown_remaining_s
        super().__init__(
            f"Circuit breaker for '{service}' is OPEN. "
            f"Cooldown: {cooldown_remaining_s:.0f}s remaining. "
            "Not retrying — fail fast."
        )


class RouterConfidenceTooLowError(Exception):
    """Not raised externally; used internally to signal clarification needed."""
    pass


class SSRFViolationError(Exception):
    """
    Raised when a PDF/URL fetch violates the SSRF guard policy.
    Policy: HTTPS only, arxiv.org allowlist, 10 MB size limit, no redirects.
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"SSRF policy violation: {reason}")
