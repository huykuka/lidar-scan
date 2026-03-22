import {computed, inject, Injectable} from '@angular/core';
import {SignalsSimpleStoreService} from '../signals-simple-store.service';
import {Edge, NodeConfig, NodeDefinition} from '../../models/node.model';
import {StatusWebSocketService} from '../status-websocket.service';
import {NodeStatusUpdate} from '@core/models';
import {DagApiService} from '@core/services/api';

export interface NodeState {
  nodes: NodeConfig[];
  edges: Edge[];
  nodeDefinitions: NodeDefinition[];
  isLoading: boolean;
  selectedNode: Partial<NodeConfig>;
  availablePipelines: string[];
  editMode: boolean;
}

const initialState: NodeState = {
  nodes: [],
  edges: [],
  nodeDefinitions: [],
  isLoading: false,
  selectedNode: {},
  availablePipelines: [],
  editMode: false,
};

@Injectable({
  providedIn: 'root',
})
export class NodeStoreService extends SignalsSimpleStoreService<NodeState> {
  private statusWebSocket = inject(StatusWebSocketService);
  private dagApi = inject(DagApiService);

  // Reactive Selectors
  nodes = this.select('nodes');
  edges = this.select('edges');
  nodeDefinitions = this.select('nodeDefinitions');
  isLoading = this.select('isLoading');
  selectedNode = this.select('selectedNode');

  // Computed status map: O(1) lookup by node_id
  nodeStatusMap = computed<Map<string, NodeStatusUpdate>>(() => {
    const statuses = this.statusWebSocket.status()?.nodes ?? [];
    return new Map(statuses.map(s => [s.node_id, s]));
  });

  // Computed Filters
  calibrationNodes = computed(() => this.nodes().filter((n) => n.category === 'calibration'));

  constructor() {
    super();
    this.setState(initialState);
  }

  /**
   * Fetches the DAG config from the backend and populates the node/edge state.
   * No-ops if nodes are already loaded to avoid redundant HTTP calls when
   * navigating from a page (e.g. Settings) that already populated the store.
   */
  async loadNodesIfEmpty(): Promise<void> {
    if (this.nodes().length > 0) return;
    try {
      const config = await this.dagApi.getDagConfig();
      this.setState({ nodes: config.nodes, edges: config.edges });
    } catch {
      // Silently ignore — callers can show their own error UI
    }
  }
}
