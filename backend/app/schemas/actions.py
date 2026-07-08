from typing import Literal

from pydantic import BaseModel

DocumentActionType = Literal["replace_selection"]


class ReplaceSelectionAction(BaseModel):
    type: Literal["replace_selection"]
    title: str
    original_text: str
    proposed_text: str
    rationale: str
    created_at: str
    rationale_source: Literal["llm", "fallback"] = "llm"


DocumentAction = ReplaceSelectionAction
