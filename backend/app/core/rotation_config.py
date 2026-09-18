from pydantic import BaseModel, Field

class RotationConfig(BaseModel):
    opening_minutes: int = Field(default=3, ge=0)
    closing_minutes: int = Field(default=2, ge=0)
    transition_minutes_each: int = Field(default=1, ge=0)
    min_group_attention_minutes: int = Field(default=3, gt=0)
    algorithm_version: str = Field(default="v1", min_length=1)

# Central instance
ROTATION_CONFIG = RotationConfig()
