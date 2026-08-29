from pydantic import BaseModel, Field

IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"


class ChatRequest(BaseModel):
    thread_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=IDENTIFIER_PATTERN,
    )
    message: str = Field(
        min_length=1,
        max_length=1000,
    )


class ApprovalRequest(BaseModel):
    thread_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=IDENTIFIER_PATTERN,
    )
    approved: bool