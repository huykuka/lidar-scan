import { Edge, NodeConfig, NodeDefinition } from '@core/models/node.model';

export interface ValidationError {
  nodeId: string;
  nodeName: string;
  field?: string;
  message: string;
}

/**
 * Detects cycles in the DAG using DFS with visited + inStack sets.
 * Returns an array of human-readable cycle descriptions.
 */
export function detectCycles(nodes: NodeConfig[], edges: Edge[]): ValidationError[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Build adjacency list
  const adjacency = new Map<string, string[]>();
  for (const n of nodes) {
    adjacency.set(n.id, []);
  }
  for (const e of edges) {
    const targets = adjacency.get(e.source_node);
    if (targets) {
      targets.push(e.target_node);
    }
  }

  const visited = new Set<string>();
  const inStack = new Set<string>();
  const errors: ValidationError[] = [];

  function dfs(nodeId: string, path: string[]): void {
    if (inStack.has(nodeId)) {
      // Reconstruct cycle path
      const cycleStart = path.indexOf(nodeId);
      const cyclePath = path.slice(cycleStart).concat(nodeId);
      const nodeNames = cyclePath.map((id) => nodeMap.get(id)?.name ?? id);
      const node = nodeMap.get(nodeId);
      errors.push({
        nodeId,
        nodeName: node?.name ?? nodeId,
        message: `Cycle detected: ${nodeNames.join(' → ')}`,
      });
      return;
    }
    if (visited.has(nodeId)) return;

    visited.add(nodeId);
    inStack.add(nodeId);
    path.push(nodeId);

    for (const neighbor of adjacency.get(nodeId) ?? []) {
      dfs(neighbor, path);
    }

    path.pop();
    inStack.delete(nodeId);
  }

  for (const n of nodes) {
    if (!visited.has(n.id)) {
      dfs(n.id, []);
    }
  }

  return errors;
}

/**
 * Validates that all required properties (per NodeDefinition) are present
 * and non-empty for every node in the graph.
 */
export function validateRequiredFields(
  nodes: NodeConfig[],
  definitions: NodeDefinition[],
): ValidationError[] {
  const defMap = new Map(definitions.map((d) => [d.type, d]));
  const errors: ValidationError[] = [];

  for (const node of nodes) {
    const def = defMap.get(node.type);
    if (!def) continue;

    for (const prop of def.properties) {
      if (!prop.required) continue;

      const value = node.config[prop.name];
      const isEmpty =
        value === null ||
        value === undefined ||
        value === '' ||
        (Array.isArray(value) && value.length === 0);

      if (isEmpty) {
        errors.push({
          nodeId: node.id,
          nodeName: node.name,
          field: prop.name,
          message: `Node "${node.name}": required field "${prop.label || prop.name}" is missing.`,
        });
      }
    }
  }

  return errors;
}
