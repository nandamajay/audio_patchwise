from pydantic import BaseModel, Field


class PatchSubmitRequest(BaseModel):
    session_id: str
    patch_input: str = Field(min_length=1)


class PatchResponse(BaseModel):
    patch_id: str
    session_id: str
    status: str
    current_patch: str
