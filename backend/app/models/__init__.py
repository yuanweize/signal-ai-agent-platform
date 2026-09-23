"""
ORM Models — re-export all models for convenient imports.

Usage:
    from app.models import User, Product, Order, ...
"""

from app.models.ai import (
    AIDecisionType,
    AIModelCall,
    AIRun,
    AISuggestion,
    AISuggestionStatus,
    EvaluationCaseResult,
    EvaluationRun,
    FeedbackEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    LearningCandidate,
    MCPServerConfig,
    MemoryItem,
    PromptVersion,
    ToolInvocation,
    TrainingExample,
)
from app.models.audit import AuditLog
from app.models.campaign import CampaignDeliveryLog
from app.models.config import BotConfig
from app.models.conversation import (
    Conversation,
    ConversationMode,
    ConversationReadState,
    ConversationType,
    Message,
    MessageActor,
    MessageAttachment,
    MessageDeliveryStatus,
    MessageDirection,
    MessageOrigin,
    MessageReaction,
)
from app.models.group import Group, GroupMember
from app.models.order import Order
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User, UserIdentity

__all__ = [
    "User",
    "UserIdentity",
    "Product",
    "Order",
    "Conversation",
    "ConversationMode",
    "ConversationType",
    "ConversationReadState",
    "Message",
    "MessageDirection",
    "MessageActor",
    "MessageDeliveryStatus",
    "MessageOrigin",
    "MessageAttachment",
    "MessageReaction",
    "Group",
    "GroupMember",
    "Payment",
    "BotConfig",
    "AuditLog",
    "CampaignDeliveryLog",
    # AI Platform v0.4
    "AIRun",
    "AISuggestion",
    "AISuggestionStatus",
    "AIDecisionType",
    "KnowledgeSource",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "MemoryItem",
    "FeedbackEvent",
    "LearningCandidate",
    "TrainingExample",
    "PromptVersion",
    "MCPServerConfig",
    "ToolInvocation",
    # AI Platform v0.4.1 Observability
    "AIModelCall",
    "EvaluationRun",
    "EvaluationCaseResult",
]
