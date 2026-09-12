from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

class PricingModel(str, Enum):
    FREE = "FREE"
    FREEMIUM = "FREEMIUM"
    PAID = "PAID"
    ENTERPRISE = "ENTERPRISE"

class SourceMetadata(BaseModel):
    name: str = Field(...)
    url: str = Field(...)

class StartupData(BaseModel):
    employeeCount: Optional[int] = Field(
        default=None, 
        description="Number of employees if explicitly stated. Never infer."
    )

class StartupContent(BaseModel):
    entityName: str = Field(...)
    data: StartupData = Field(default_factory=StartupData)

class StartupEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    schemaVersion: str = Field(default="1.0")
    recordType: str = Field(default="STARTUP")
    source: SourceMetadata
    content: StartupContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)

class ProductContent(BaseModel):
    startupName: str = Field(...)
    pricingModel: Optional[PricingModel] = Field(None)

class ProductEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    schemaVersion: str = Field(default="1.0")
    recordType: str = Field(default="PRODUCT")
    source: SourceMetadata
    content: ProductContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)

class ResearchPaperContent(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    paper_url: str
    github_url: Optional[str] = None
    github_stars: Optional[int] = None
    published_date: datetime

class ResearchPaperEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    schemaVersion: str = Field(default="1.0")
    recordType: str = Field(default="RESEARCH_PAPER")
    source: SourceMetadata
    content: ResearchPaperContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)

class NewsContent(BaseModel):
    title: str = Field(...)
    body: str = Field(...)
    published_date: datetime = Field(...)


class NewsEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = Field(default="1.0")
    recordType: str = Field(default="NEWS")
    source: SourceMetadata
    content: NewsContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class JobContent(BaseModel):
    company: str = Field(...)
    date: datetime = Field(...)
    is_remote: Optional[bool] = Field(default=None)
    role_family: Optional[str] = Field(default=None)
    title: str = Field(...)
    job_url: str = Field(...)


class JobEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: str = Field(default="1.0")
    recordType: str = Field(default="JOB")
    source: SourceMetadata
    content: JobContent
    collectedAt: datetime = Field(default_factory=datetime.utcnow)


class MatchMethod(str, Enum):
    EXACT = "EXACT"
    FUZZY = "FUZZY"
    LLM_TIEBREAK = "LLM_TIEBREAK"


class EntityMappingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str = Field(...)
    canonical_name: str = Field(...)
    entity_type: str = Field(...)
    resolution_method: MatchMethod = Field(...)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    source_url: str = Field(...)
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
