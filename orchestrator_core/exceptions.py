"""
orchestrator_core/exceptions.py

All custom exceptions for the v2 FastAPI service.
Centralised here so they can be imported without pulling in any agent or storage code.
"""


class ApprovalNotFoundError(Exception):
    """Raised when execute_approved() is called with an id that has no DB row."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval record not found: {approval_id}")


class ApprovalNotGrantedError(Exception):
    """Raised when execute_approved() is called on a record whose status is not 'approved'."""
    def __init__(self, approval_id: str, status: str):
        self.approval_id = approval_id
        self.status = status
        super().__init__(f"Approval {approval_id} is in state '{status}', expected 'approved'")


class ApprovalExpiredError(Exception):
    """Raised when execute_approved() is called on a record that has passed its expires_at."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval {approval_id} has expired and can no longer be executed")


class ApprovalAlreadyExecutedError(Exception):
    """Raised when execute_approved() is called on a record that is already in 'executed' state."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Approval {approval_id} was already executed — cannot execute twice")


class ApprovalClaimConflictError(Exception):
    """Raised when the compare-and-set claim for 'executing' state fails (concurrent call won)."""
    def __init__(self, approval_id: str):
        self.approval_id = approval_id
        super().__init__(f"Another process already claimed execution of approval {approval_id}")


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
