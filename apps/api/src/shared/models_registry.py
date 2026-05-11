"""
统一 import 所有 ORM 模型,让 Base.metadata 收齐全部 table 定义。

alembic env.py 和需要 metadata 的地方都从这里 import Base。
"""
# noqa: F401 — 这些 import 是为了让 SQLAlchemy 注册 metadata,不直接使用
from src.auth.models import User, UserProfile  # noqa: F401
from src.md.models import MdDocument, MdSegment  # noqa: F401
from src.match.models import Match, Matchpoint, MatchHook  # noqa: F401
from src.agent_chat.models import AgentChat, AgentChatMessage  # noqa: F401
from src.room.models import UserSoftBlocklist, UserHardBlocklist  # noqa: F401
from src.summary.models import Summary, SummaryDecision  # noqa: F401
from src.human_chat.models import (  # noqa: F401
    ChatSession,
    ChatMessage,
    ChatCallout,
    ChatReport,
)
from src.llm.models import PromptVersion, LlmCallLog  # noqa: F401
from src.agent_self.models import (  # noqa: F401
    AgentConversation,
    AgentConversationMessage,
)
from src.shared.base import Base  # noqa: F401

__all__ = ["Base"]
