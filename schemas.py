# schemas.py

from pydantic import BaseModel, Field, create_model
from typing import Optional, List, Dict, Type

class JobStatus(BaseModel):
    """Defines the schema for a job's status response."""
    job_id: str
    status: str
    details: str
    total_groups: int = 0
    groups_processed: int = 0
    progress_percent: float = 0.0
    result_path: Optional[str] = None

class ClassificationResponse(BaseModel):
    """Defines the schema for the combined classification output from the LLM."""
    image_description: str
    image_type: str
    classified_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

def create_extraction_model(doc_type: str, fields: List[Dict]) -> Type[BaseModel]:
    """Dynamically creates a FLAT Pydantic model for detailed field extraction."""
    field_definitions = {}
    for field in fields:
        # Sanitize the field name to be a valid Python identifier for the model
        base_name = ''.join(c if c.isalnum() else '_' for c in field['name'])
        
        field_definitions[f"{base_name}_Value"] = (Optional[str], Field(default=None))
        field_definitions[f"{base_name}_Confidence"] = (Optional[float], Field(default=None, ge=0.0, le=1.0))
        field_definitions[f"{base_name}_Reasoning"] = (Optional[str], Field(default=None))
        
    model_name = f"{doc_type.capitalize().replace(' ', '')}ExtractionModel"
    return create_model(model_name, **field_definitions)