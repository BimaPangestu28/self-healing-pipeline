from pydantic import BaseModel, Field


class RouteDecision(BaseModel):
    """Structured routing decision produced by the router tier."""

    targets: list[str] = Field(default_factory=list)
    mode: str = "single"  # single | multi | clarify | reject | intro
    clarifying_question: str | None = None
    confidence: float = 0.0


class SpecialistResult(BaseModel):
    """Normalized specialist response payload."""

    target: str
    text: str


class DispatchResult(BaseModel):
    """Final dispatcher output consumed by the API layer."""

    message: str
    pending_approvals: list | None = None
