# schemas.py

from pydantic import BaseModel, Field, create_model
from typing import Optional, Any, List, Dict, Type

class JobStatus(BaseModel):
    """Defines the schema for a job's status response."""
    job_id: str
    status: str
    details: str
    total_groups: int = 0
    groups_processed: int = 0
    progress_percent: float = 0.0
    result_path: Optional[str] = None

class FieldDetail(BaseModel):
    """Defines the schema for a single extracted field's details."""
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

class ClassificationResponse(BaseModel):
    """Defines the schema for the combined classification output from the LLM."""
    image_description: str
    image_type: str
    classified_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

def create_extraction_model(doc_type: str, fields: List[Dict]) -> Type[BaseModel]:
    """Dynamically creates a Pydantic model for detailed field extraction."""
    field_definitions = {
        field['name']: (Optional[FieldDetail], Field(default=None))
        for field in fields
    }
    model_name = f"{doc_type.capitalize().replace(' ', '')}ExtractionModel"
    return create_model(model_name, **field_definitions)