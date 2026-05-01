from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    kernel_version: str = Field(default="unknown")
    subsystem: str = Field(default="alsa-asoc")
    source_path: str = Field(default="")
    llm_provider: str = Field(default="qgenie")
    llm_model: str = Field(default="gpt-4o")
    max_rounds: int = Field(default=5, ge=1, le=5)


class SessionResponse(BaseModel):
    session_id: str
    status: str
    kernel_version: str
    subsystem: str
    source_path: str
    llm_provider: str
    llm_model: str
    max_rounds: int
