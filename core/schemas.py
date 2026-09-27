from enum import Enum
from langgraph.graph import MessagesState

class RouteTarget(str, Enum):
    """Valid routing targets for the multi-agent system."""
    SQL = "sql_node"
    FINANCE = "finance_node"
    WEB_SEARCH = "web_search_node"
    MODEL = "model"


class State(MessagesState):
    """Graph state - extends MessagesState with any custom fields."""
    tool_call_count: int
    guardrail_blocked: bool
    routing_target: str
    routing_latency_ms: float