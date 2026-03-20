import {computed, inject, Injectable} from '@angular/core';
import {SignalsSimpleStoreService} from '../signals-simple-store.service';
import {Edge, NodeConfig, NodeDefinition} from '../../models/node.model';
import {StatusWebSocketService} from '../status-websocket.service';
import {NodeStatusUpdate} from '../../models/node-status.model';

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
  visibleNodes = computed(() => this.nodes().filter(n => n.visible !== false));
  sensorNodes = computed(() => this.nodes().filter((n) => n.category === 'sensor'));
  fusionNodes = computed(() => this.nodes().filter((n) => n.category === 'fusion'));
  operationNodes = computed(() => this.nodes().filter((n) => n.category === 'operation'));
  calibrationNodes = computed(() => this.nodes().filter((n) => n.category === 'calibration'));

  constructor() {
    super();
    this.setState(initialState);
  }
}
