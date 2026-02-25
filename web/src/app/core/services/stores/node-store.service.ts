import { Injectable, computed, Signal } from '@angular/core';
import { SignalsSimpleStoreService } from '../signals-simple-store.service';
import { NodeConfig, Edge, NodeDefinition } from '../../models/node.model';

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
  constructor() {
    super();
    this.setState(initialState);
  }

  // Reactive Selectors
  nodes = this.select('nodes');
  edges = this.select('edges');
  nodeDefinitions = this.select('nodeDefinitions');
  isLoading = this.select('isLoading');
  selectedNode = this.select('selectedNode');
  availablePipelines = this.select('availablePipelines');
  editMode = this.select('editMode');

  // Computed Filters
  sensorNodes = computed(() => this.nodes().filter((n) => n.category === 'sensor'));
  fusionNodes = computed(() => this.nodes().filter((n) => n.category === 'fusion'));
  operationNodes = computed(() => this.nodes().filter((n) => n.category === 'operation'));
}
