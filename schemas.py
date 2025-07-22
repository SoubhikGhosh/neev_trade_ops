from pydantic import BaseModel, Field, create_model
from typing import Optional, Any, List, Dict, Type

class JobStatus(BaseModel):
    """Defines the schema for a job's status response."""
    job_id: str
    status: str = Field(description="The current status of the job (e.g., Queued, Processing, Completed, Failed).")
    details: str = Field(description="A message describing the current progress.")
    total_groups: int = Field(0, description="Total number of document groups to process.")
    groups_processed: int = Field(0, description="Number of document groups already processed.")
    progress_percent: float = Field(0.0, ge=0.0, le=100.0, description="The completion percentage of the job.")
    result_path: Optional[str] = Field(None, description="The path to the final output file upon completion.")

class FieldDetail(BaseModel):
    """Defines the schema for a single extracted field's details."""
    value: Optional[Any] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

class ClassificationResponse(BaseModel):
    """Defines the schema for the classification output from the LLM."""
    classified_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

def create_extraction_model(doc_type: str, fields: List[Dict]) -> Type[BaseModel]:
    """Dynamically creates a Pydantic model for a given document type's extraction fields."""
    field_definitions = {
        field['name']: (FieldDetail, ...) for field in fields
    }
    model_name = f"{doc_type.capitalize()}ExtractionModel"
    return create_model(model_name, **field_definitions)