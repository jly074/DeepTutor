"""Optional original-question source labels shared by API and file imports."""

from pydantic import BaseModel, Field


class QuestionSourceMetadata(BaseModel):
    """User-supplied source labels, never inferred from a question or path."""

    filename: str = Field(default="", max_length=255)
    year: int | None = Field(default=None, ge=1, le=9999, strict=True)
    pdf_page: int | None = Field(default=None, ge=1, strict=True)
    question_number: str = Field(default="", max_length=100)
