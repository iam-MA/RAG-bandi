"""
Schema definitions for the tender analysis pipeline.
Uses Pydantic for validation and serialization.
"""
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ImportanceLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightCategory(str, Enum):
    TENDER_OVERVIEW = "tender_overview"
    REQUISITO_PARTECIPAZIONE = "requisito_partecipazione"
    CRITERIO_PUNTEGGIO = "criterio_punteggio"
    DOCUMENTO_RICHIESTO = "documento_richiesto"
    SCADENZA = "scadenza"
    SPECIFICA_TECNICA = "specifica_tecnica"


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IssueCategory(str, Enum):
    MISSING_FIELD = "missing_field"
    INCONSISTENCY = "inconsistency"
    POTENTIAL_ERROR = "potential_error"
    SUGGESTION = "suggestion"


# =============================================================================
# DOCUMENT PROFILE (Output of Analyzer Agent)
# =============================================================================

class DocumentSection(BaseModel):
    """A section identified in the document."""
    title: str
    start_line: int
    end_line: int
    content_summary: Optional[str] = None


class DocumentProfile(BaseModel):
    """
    Profile of the tender document, produced by the Analyzer Agent.
    Used by the Planner to create an extraction strategy.
    """
    # Basic info
    sector: str = Field(description="Sector of the tender (e.g., 'servizi_pulizia', 'software', 'edilizia')")
    tender_type: str = Field(description="Type of procedure (e.g., 'procedura_aperta', 'affidamento_diretto')")
    complexity: Literal["low", "medium", "high"] = Field(description="Estimated complexity")
    
    # Document structure
    total_lines: int
    total_sections: int
    language: str = "it"
    structure_quality: Literal["poor", "fair", "good", "excellent"]
    
    # Mapped sections
    sections: List[DocumentSection] = Field(default_factory=list)
    
    # Observations
    key_observations: List[str] = Field(
        default_factory=list,
        description="Notable aspects of the document structure or content"
    )


# =============================================================================
# EXTRACTION PLAN (Output of Planner Agent)
# =============================================================================

class ExtractionTask(BaseModel):
    """A single extraction task to be executed."""
    id: int
    agent_type: str = Field(description="Which agent should execute this task")
    target_sections: List[str] = Field(description="Which sections to analyze")
    focus_areas: List[str] = Field(default_factory=list, description="Specific things to look for")
    priority: Literal["high", "medium", "low"] = "medium"


class ExtractionPlan(BaseModel):
    """
    Plan created by the Planner Agent for extracting information.
    """
    strategy: str = Field(description="Overall extraction strategy")
    tasks: List[ExtractionTask]
    estimated_api_calls: int
    notes: Optional[str] = None


# =============================================================================
# INSIGHT (Output of Executor Agents)
# =============================================================================

class Finding(BaseModel):
    """What was found in the document."""
    title: str
    description: str
    source_text: Optional[str] = Field(None, description="Original text from document")
    source_location: Optional[str] = Field(None, description="Where in the document")


class Impact(BaseModel):
    """Why this finding matters."""
    importance: ImportanceLevel
    reason: str
    points_available: Optional[int] = Field(None, description="For scoring criteria")


class Action(BaseModel):
    """What the user can do about this."""
    suggestion: str
    documents_needed: List[str] = Field(default_factory=list)
    preparation_hint: Optional[str] = None


class InsightMetadata(BaseModel):
    """Metadata about the extraction."""
    confidence: float = Field(ge=0, le=1)
    extracted_by: str
    verified: bool = False


class Insight(BaseModel):
    """
    A single actionable insight extracted from the tender.
    This is the core unit of output.
    """
    id: str
    category: InsightCategory
    type: str
    
    finding: Finding
    impact: Impact
    action: Action
    metadata: InsightMetadata


# =============================================================================
# FINAL OUTPUT
# =============================================================================

class TenderSummary(BaseModel):
    """Quick summary of the tender."""
    title: str
    contracting_authority: Optional[str] = None
    value: Optional[float] = None
    duration_months: Optional[int] = None
    sector: str
    procedure: Optional[str] = None


class ActionSummary(BaseModel):
    """Summary of actions for the user."""
    critical_requirements: int = 0
    documents_to_prepare: int = 0
    days_until_deadline: Optional[int] = None
    potential_extra_points: int = 0
    key_focus_areas: List[str] = Field(default_factory=list)


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""
    document_name: str
    extraction_date: datetime = Field(default_factory=datetime.now)
    pipeline_version: str = "2.0"
    confidence_overall: float = Field(ge=0, le=1)
    warnings: List[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """
    Complete output of the extraction pipeline.
    """
    extraction_metadata: ExtractionMetadata
    tender_summary: TenderSummary
    insights: List[Dict[str, Any]] = Field(default_factory=list)
    action_summary: ActionSummary
    
    # Raw data for debugging
    document_profile: Optional[DocumentProfile] = None
    extraction_plan: Optional[ExtractionPlan] = None


# =============================================================================
# VALIDATION RESULT (Output of Validator Agent)
# =============================================================================

class ValidationIssue(BaseModel):
    """A single issue found during validation."""
    severity: str = Field(description="critical, warning, or info")
    category: str = Field(description="missing_field, inconsistency, potential_error, or suggestion")
    field: str = Field(description="Name of the problematic field")
    description: str
    suggested_action: Optional[str] = None


class ValidationResult(BaseModel):
    """
    Result of validation by the Validator Agent.
    """
    quality_score: float = Field(ge=0, le=1, description="Overall quality score")
    is_complete: bool = Field(description="Whether extraction is complete (no critical issues)")
    
    total_issues: int = 0
    critical_issues: int = 0
    warning_issues: int = 0
    info_issues: int = 0
    
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    validated_at: datetime = Field(default_factory=datetime.now)
