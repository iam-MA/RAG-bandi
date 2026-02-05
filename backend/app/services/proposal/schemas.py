"""
Data Models for Pipeline 2 - Professional Proposal Generation

Pydantic models for strong typing and validation across all agents.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class TenderType(str, Enum):
    """Types of tender procedures."""
    PROCEDURA_APERTA = "procedura_aperta"
    PROCEDURA_RISTRETTA = "procedura_ristretta"
    PROCEDURA_NEGOZIATA = "procedura_negoziata"
    AFFIDAMENTO_DIRETTO = "affidamento_diretto"
    ALTRO = "altro"


class AwardCriteria(str, Enum):
    """Tender award criteria."""
    OEPV = "offerta_economicamente_piu_vantaggiosa"  # Quality + Price
    PREZZO_PIU_BASSO = "prezzo_piu_basso"  # Price only
    COSTO_FISSO = "costo_fisso"  # Fixed cost, quality only


class Sector(str, Enum):
    """Tender sectors."""
    SERVIZI_PULIZIA = "servizi_pulizia"
    SOFTWARE = "software"
    EDILIZIA = "edilizia"
    SANITA = "sanita"
    TRASPORTI = "trasporti"
    FORMAZIONE = "formazione"
    CONSULENZA = "consulenza"
    FORNITURE = "forniture"
    ALTRO = "altro"


class Importance(str, Enum):
    """Requirement importance levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Complexity(str, Enum):
    """Tender complexity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Tender Analysis Models
# =============================================================================

class ScoringCriterion(BaseModel):
    """A single scoring criterion from the tender."""
    id: str
    name: str
    description: str
    max_points: float
    weight: Optional[float] = None
    sub_criteria: Optional[List["ScoringCriterion"]] = None
    source_text: Optional[str] = None


class CriticalRequirement(BaseModel):
    """A critical requirement that must be met."""
    id: str
    category: str
    description: str
    importance: Importance
    is_mandatory: bool = True
    source_text: Optional[str] = None


class TenderProfile(BaseModel):
    """Complete profile of the analyzed tender."""
    tender_id: str
    tender_type: TenderType
    sector: Sector
    award_criteria: AwardCriteria
    
    # Scoring weights
    technical_weight: float = Field(ge=0, le=100, description="Weight of technical offer (0-100)")
    economic_weight: float = Field(ge=0, le=100, description="Weight of economic offer (0-100)")
    
    # Requirements analysis
    critical_requirements: List[CriticalRequirement] = []
    scoring_criteria: List[ScoringCriterion] = []
    total_technical_points: float = 0
    
    # Complexity assessment
    estimated_complexity: Complexity = Complexity.MEDIUM
    key_themes: List[str] = []
    
    # Original data
    title: Optional[str] = None
    contracting_authority: Optional[str] = None
    estimated_value: Optional[float] = None
    deadline: Optional[datetime] = None
    duration_months: Optional[int] = None


# =============================================================================
# Proposal Planning Models
# =============================================================================

class SectionRequirement(BaseModel):
    """A requirement to be addressed in a section."""
    id: str
    description: str
    importance: Importance
    max_points: Optional[float] = None
    source_text: Optional[str] = None
    insight_id: Optional[str] = None  # Reference to tender_insights


class PlannedSection(BaseModel):
    """A planned section of the proposal."""
    id: str
    title: str
    order: int
    target_words: int = Field(ge=100, le=5000)
    requirements: List[SectionRequirement] = []
    kb_queries: List[str] = []  # Queries to search in company KB
    max_points: float = 0
    instructions: str = ""  # Specific writing instructions
    

class ProposalOutline(BaseModel):
    """Complete outline for the proposal."""
    sections: List[PlannedSection]
    total_target_words: int
    estimated_pages: int
    
    # Strategy notes
    key_differentiators: List[str] = []  # What to emphasize
    risks_to_address: List[str] = []  # Potential weaknesses
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Knowledge Base Models
# =============================================================================

class KBMatch(BaseModel):
    """A match from the company knowledge base."""
    chunk_id: str
    content: str
    similarity: float = Field(ge=0, le=1)
    source_document: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def get_citation(self) -> str:
        """Generate a citation for this match."""
        if self.source_document:
            return f"[Fonte: {self.source_document}]"
        return f"[Fonte: KB-{self.chunk_id[:8]}]"


class SectionContext(BaseModel):
    """Retrieved context for a section."""
    section_id: str
    matches: List[KBMatch] = []
    total_matches: int = 0
    avg_similarity: float = 0
    
    def has_sufficient_context(self, min_matches: int = 1, min_similarity: float = 0.5) -> bool:
        """Check if there's enough context to write the section."""
        relevant = [m for m in self.matches if m.similarity >= min_similarity]
        return len(relevant) >= min_matches


# =============================================================================
# Section Writing Models
# =============================================================================

class MissingData(BaseModel):
    """Data that is missing and needs to be provided."""
    description: str
    importance: Importance
    suggested_source: Optional[str] = None  # e.g., "certificazione ISO 9001"


class WrittenSection(BaseModel):
    """A generated section of the proposal."""
    id: str
    title: str
    content: str
    word_count: int
    
    # Traceability
    sources_used: List[str] = []  # Document names
    source_citations: List[KBMatch] = []  # Full citation data
    missing_data: List[MissingData] = []
    
    # Coverage
    requirements_addressed: List[str] = []  # Requirement IDs
    points_targeted: float = 0
    
    # Metadata
    generation_time_ms: int = 0
    model_used: str = ""


# =============================================================================
# Quality Validation Models
# =============================================================================

class ValidationIssue(BaseModel):
    """An issue found during validation."""
    severity: str  # "error", "warning", "info"
    category: str  # "coverage", "source", "length", "hallucination", "consistency"
    message: str
    location: Optional[str] = None  # e.g., "paragraph 3"
    suggestion: Optional[str] = None


class QualityReport(BaseModel):
    """Quality validation report for a section."""
    section_id: str
    passed: bool
    
    # Scores (0-1)
    coverage_score: float = Field(ge=0, le=1, description="% of requirements covered")
    source_coverage: float = Field(ge=0, le=1, description="% of claims with sources")
    length_compliance: float = Field(ge=0, le=1, description="Compliance with target length")
    
    # Issues
    issues: List[ValidationIssue] = []
    
    # Counts
    requirements_covered: int = 0
    requirements_total: int = 0
    claims_with_sources: int = 0
    claims_total: int = 0
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


class ValidatedSection(BaseModel):
    """A section that has passed validation."""
    section: WrittenSection
    quality_report: QualityReport
    
    # If validation failed, this contains the revised content
    was_revised: bool = False
    revision_notes: Optional[str] = None


# =============================================================================
# Final Proposal Models
# =============================================================================

class ProposalMetadata(BaseModel):
    """Metadata about the generated proposal."""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    tender_id: str
    tender_cig: Optional[str] = None
    company_id: str
    company_name: Optional[str] = None
    
    # Statistics
    total_sections: int = 0
    total_words: int = 0
    estimated_pages: int = 0
    total_points_targeted: float = 0
    
    # Coverage
    requirements_total: int = 0
    requirements_addressed: int = 0
    coverage_percentage: float = 0
    
    # Quality
    avg_source_coverage: float = 0
    total_missing_data: int = 0
    
    # Timing
    total_generation_time_ms: int = 0


class MissingDataSummary(BaseModel):
    """Summary of all missing data across the proposal."""
    items: List[MissingData] = []
    
    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.items if i.importance == Importance.CRITICAL)
    
    @property
    def high_count(self) -> int:
        return sum(1 for i in self.items if i.importance == Importance.HIGH)


class GeneratedProposal(BaseModel):
    """The complete generated proposal."""
    metadata: ProposalMetadata
    
    # Content
    executive_summary: Optional[str] = None
    table_of_contents: List[Dict[str, Any]] = []
    sections: List[ValidatedSection] = []
    
    # Analysis
    tender_profile: TenderProfile
    missing_data_summary: MissingDataSummary = Field(default_factory=MissingDataSummary)
    
    # Quality
    overall_quality_score: float = Field(ge=0, le=100, default=0)
    quality_notes: List[str] = []
    
    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for database storage."""
        return self.model_dump(mode="json")
