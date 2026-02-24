/**
 * Base interface for all node types in the flow canvas
 */
export interface NodePlugin {
  /** Unique identifier for this node type */
  type: string;
  
  /** Display name shown in the palette */
  displayName: string;
  
  /** Description shown in the palette */
  description: string;
  
  /** Icon name (Synergy Design System icon) */
  icon: string;
  
  /** Visual styling */
  style: {
    /** Border and accent color */
    color: string;
    /** Background color */
    backgroundColor: string;
  };
  
  /** Port configuration */
  ports?: {
    /** Input ports (left side) */
    inputs?: PortDefinition[];
    /** Output ports (right side) */
    outputs?: PortDefinition[];
  };
  
  /** Factory function to create a new instance */
  createInstance: () => NodeData;
  
  /** Renderer for the node body content */
  renderBody?: (data: NodeData) => NodeBodyTemplate;
  
  /** Validator for node data */
  validate?: (data: NodeData) => ValidationResult;
  
  /** Editor component for node configuration */
  editorComponent?: any; // Angular component class
}

/**
 * Port definition for node connections
 */
export interface PortDefinition {
  /** Port identifier */
  id: string;
  
  /** Display label */
  label: string;
  
  /** Data type for validation */
  dataType: string;
  
  /** Whether multiple connections are allowed */
  multiple?: boolean;
}

/**
 * Generic node data structure
 */
export interface NodeData {
  id?: string;
  type: string;
  name: string;
  enabled?: boolean;
  [key: string]: any; // Plugin-specific data
}

/**
 * Template for rendering node body
 */
export interface NodeBodyTemplate {
  fields: Array<{
    label: string;
    value: string | number | boolean;
    type?: 'text' | 'number' | 'boolean' | 'badge';
  }>;
}

/**
 * Validation result
 */
export interface ValidationResult {
  valid: boolean;
  errors?: string[];
  warnings?: string[];
}

/**
 * Connection between nodes
 */
export interface NodeConnection {
  id: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
}
