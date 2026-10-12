import {Edge, NodeConfig} from '@core/models/node.model';

/** Enabled nodes reachable downstream of ``rootId`` (inclusive). Mirrors the backend. */
export function downstreamNodes(rootId: string, nodes: NodeConfig[], edges: Edge[]): NodeConfig[] {
  const enabled = new Map(nodes.filter((n) => n.enabled).map((n) => [n.id, n]));
  if (!enabled.has(rootId)) return [];
  const next = new Map<string, string[]>();
  for (const e of edges) {
    if (!e.source_node || !e.target_node) continue;
    next.set(e.source_node, [...(next.get(e.source_node) ?? []), e.target_node]);
  }
  const seen = new Set([rootId]);
  const stack = [rootId];
  while (stack.length) {
    for (const id of next.get(stack.pop()!) ?? []) {
      if (enabled.has(id) && !seen.has(id)) {
        seen.add(id);
        stack.push(id);
      }
    }
  }
  return [...seen].map((id) => enabled.get(id)!);
}

/** Default nodes whose clouds are worth capturing: final nodes plus the nodes feeding them. */
export function defaultCaptureIds(subgraph: NodeConfig[], edges: Edge[]): string[] {
  const ids = new Set(subgraph.map((n) => n.id));
  const inGraph = edges.filter((e) => ids.has(e.source_node) && ids.has(e.target_node));
  const hasOut = new Set(inGraph.map((e) => e.source_node));
  const leaves = subgraph.map((n) => n.id).filter((id) => !hasOut.has(id));
  const parents = inGraph.filter((e) => leaves.includes(e.target_node)).map((e) => e.source_node);
  return [...new Set([...parents, ...leaves])];
}
