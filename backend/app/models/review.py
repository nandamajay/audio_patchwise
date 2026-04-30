from pydantic import BaseModel


class ReviewFinding(BaseModel):
    issue_type: str
    severity: str
    line_number: int
    description: str
    suggestion: str


class ReviewRound(BaseModel):
    round: int
    findings: list[ReviewFinding]
    quality_score: float
    verdict: str
