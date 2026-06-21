from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState

class RouteTarget(str, Enum):
    """Valid routing targets for the multi-agent system."""
    SQL = "sql_node"
    FINANCE = "finance_node"
    WEB_SEARCH = "web_search_node"
    MODEL = "model"


class RouterDecision(BaseModel):
    """Structured output for router (no longer used with fast routing)."""
    target: RouteTarget
    reason: str = Field(description="Brief explanation of routing decision")


class State(MessagesState):
    """Graph state - extends MessagesState with any custom fields."""
    tool_call_count: int = 0