from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

class PropertySchema(BaseModel):
    """
    Schema definition for a configurable property in a node.
    
    Property is shown in UI only when ALL key-value constraints in depends_on are satisfied 
    (AND relationship). Each list contains the allowed values for that key.
    """
    name: str
    label: str
    type: str  # "string", "number", "boolean", "select", "vec3", "list", "pose"
    default: Optional[Any] = None
    options: Optional[List[Dict[str, Any]]] = None  # For "select" type
    required: bool = False
    help_text: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    hidden: bool = False  # Hide from UI but keep in schema
    depends_on: Optional[Dict[str, List[Any]]] = None

class PortSchema(BaseModel):
    id: str
    label: str
    data_type: str = "pointcloud"
    multiple: bool = False

class NodeDefinition(BaseModel):
    type: str
    display_name: str
    category: str  # "sensor", "fusion", "operation"
    description: Optional[str] = None
    icon: str = "settings_input_component"
    websocket_enabled: bool = True  # When False, node does not stream data; hides visibility & recording controls in UI
    properties: List[PropertySchema] = []
    inputs: List[PortSchema] = []
    outputs: List[PortSchema] = []

class SchemaRegistry:
    def __init__(self):
        self._definitions: Dict[str, NodeDefinition] = {}

    def register(self, definition: NodeDefinition):
        try:
            with open("/tmp/node_registry_debug.log", "a") as f:
                f.write(f"DEBUG: Registering node type: {definition.type}\n")
        except:
            pass
        self._definitions[definition.type] = definition

    def get_all(self) -> List[NodeDefinition]:
        return list(self._definitions.values())

    def get(self, type_name: str) -> Optional[NodeDefinition]:
        return self._definitions.get(type_name)

node_schema_registry = SchemaRegistry()
