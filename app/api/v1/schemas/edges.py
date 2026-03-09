"""Edge-related schema models for DAG connections."""

from pydantic import BaseModel


class EdgeRecord(BaseModel):
    """DAG edge connection record."""
    id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str