"""
Agents package for the tender analysis pipeline.
Contains all specialized agents for multi-step document analysis.
"""

from .base_agent import BaseAgent, AgentResult
from .agent_schemas import (
    # Enums
    ImportanceLevel,
    InsightCategory,
    IssueSeverity,
    IssueCategory,
    # Document Profile
    DocumentSection,
    DocumentProfile,
    # Extraction Plan
    ExtractionTask,
    ExtractionPlan,
    # Insight
    Finding,
    Impact,
    Action,
    InsightMetadata,
    Insight,
    # Final Output
    TenderSummary,
    ActionSummary,
    ExtractionMetadata,
    ExtractionResult,
    # Validation
    ValidationIssue,
    ValidationResult,
)
from .analyzer_agent import AnalyzerAgent
from .planner_agent import PlannerAgent
from .executor_agents import (
    BaseExecutorAgent,
    GeneralInfoExtractor,
    RequirementsExtractor,
    ScoringExtractor,
    DocumentsExtractor,
    DeadlinesExtractor,
    TechnicalSpecsExtractor,
    EXECUTOR_REGISTRY,
    get_executor,
)
from .aggregator_agent import AggregatorAgent
from .validator_agent import ValidatorAgent

__all__ = [
    # Base
    "BaseAgent",
    "AgentResult",
    # Schemas
    "ImportanceLevel",
    "InsightCategory",
    "IssueSeverity",
    "IssueCategory",
    "DocumentSection",
    "DocumentProfile",
    "ExtractionTask",
    "ExtractionPlan",
    "Finding",
    "Impact",
    "Action",
    "InsightMetadata",
    "Insight",
    "TenderSummary",
    "ActionSummary",
    "ExtractionMetadata",
    "ExtractionResult",
    "ValidationIssue",
    "ValidationResult",
    # Agents
    "AnalyzerAgent",
    "PlannerAgent",
    "BaseExecutorAgent",
    "GeneralInfoExtractor",
    "RequirementsExtractor",
    "ScoringExtractor",
    "DocumentsExtractor",
    "DeadlinesExtractor",
    "TechnicalSpecsExtractor",
    "EXECUTOR_REGISTRY",
    "get_executor",
    "AggregatorAgent",
    "ValidatorAgent",
]
