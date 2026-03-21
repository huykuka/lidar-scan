import { TestBed } from '@angular/core/testing';
import { CanvasEditStoreService } from './canvas-edit-store.service';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { DagApiService } from '@core/services/api/dag-api.service';
import { ToastService } from '@core/services/toast.service';
import { DialogService } from '@core/services/dialog.service';
import { NodesApiService } from '@core/services/api/nodes-api.service';
import { NodeConfig, Edge } from '@core/models/node.model';
import { DagConfigResponse } from '@core/models/dag.model';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const makeNode = (id: string, overrides: Partial<NodeConfig> = {}): NodeConfig => ({
  id,
  name: `Node ${id}`,
  type: 'sensor',
  category: 'sensor',
  enabled: true,
  visible: true,
  config: {},
  x: 0,
  y: 0,
  ...overrides,
});

const makeEdge = (id: string, sourceNode: string, targetNode: string): Edge => ({
  id,
  source_node: sourceNode,
  source_port: 'out',
  target_node: targetNode,
  target_port: 'in',
});

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------
function createNodeStoreMock() {
  let nodesValue: NodeConfig[] = [];
  let edgesValue: Edge[] = [];
  const nodesSignal = jasmine.createSpy('nodes').and.callFake(() => nodesValue);
  const edgesSignal = jasmine.createSpy('edges').and.callFake(() => edgesValue);
  return {
    nodes: nodesSignal,
    edges: edgesSignal,
    setState: jasmine.createSpy('setState').and.callFake((state: any) => {
      if (state.nodes !== undefined) nodesValue = state.nodes;
      if (state.edges !== undefined) edgesValue = state.edges;
    }),
    _setNodes: (n: NodeConfig[]) => { nodesValue = n; },
    _setEdges: (e: Edge[]) => { edgesValue = e; },
  };
}

function createDagApiMock() {
  return {
    getDagConfig: jasmine.createSpy('getDagConfig').and.returnValue(
      Promise.resolve({ config_version: 5, nodes: [], edges: [] } as DagConfigResponse),
    ),
    saveDagConfig: jasmine.createSpy('saveDagConfig').and.returnValue(
      Promise.resolve({ config_version: 6, node_id_map: {} }),
    ),
  };
}

function createToastMock() {
  return {
    success: jasmine.createSpy('success'),
    danger: jasmine.createSpy('danger'),
    warning: jasmine.createSpy('warning'),
  };
}

function createDialogMock() {
  return {
    confirm: jasmine.createSpy('confirm').and.returnValue(Promise.resolve(true)),
  };
}

function createNodesApiMock() {
  return {
    reloadConfig: jasmine.createSpy('reloadConfig').and.returnValue(Promise.resolve({})),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('CanvasEditStoreService', () => {
  let service: CanvasEditStoreService;
  let nodeStoreMock: ReturnType<typeof createNodeStoreMock>;
  let dagApiMock: ReturnType<typeof createDagApiMock>;
  let toastMock: ReturnType<typeof createToastMock>;
  let dialogMock: ReturnType<typeof createDialogMock>;
  let nodesApiMock: ReturnType<typeof createNodesApiMock>;

  beforeEach(() => {
    nodeStoreMock = createNodeStoreMock();
    dagApiMock = createDagApiMock();
    toastMock = createToastMock();
    dialogMock = createDialogMock();
    nodesApiMock = createNodesApiMock();

    TestBed.configureTestingModule({
      providers: [
        CanvasEditStoreService,
        { provide: NodeStoreService, useValue: nodeStoreMock },
        { provide: DagApiService, useValue: dagApiMock },
        { provide: ToastService, useValue: toastMock },
        { provide: DialogService, useValue: dialogMock },
        { provide: NodesApiService, useValue: nodesApiMock },
      ],
    });
    service = TestBed.inject(CanvasEditStoreService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // initFromBackend
  // -------------------------------------------------------------------------
  describe('initFromBackend()', () => {
    it('should seed localNodes, localEdges, and baseVersion', () => {
      const nodes = [makeNode('n1')];
      const edges = [makeEdge('e1', 'n1', 'n2')];
      service.initFromBackend({ config_version: 7, nodes, edges });

      expect(service.localNodes()).toEqual(nodes);
      expect(service.localEdges()).toEqual(edges);
      expect(service.baseVersion()).toBe(7);
    });

    it('should call nodeStore.setState with the given nodes and edges', () => {
      const nodes = [makeNode('n1')];
      service.initFromBackend({ config_version: 1, nodes, edges: [] });
      expect(nodeStoreMock.setState).toHaveBeenCalledWith({ nodes, edges: [] });
    });
  });

  // -------------------------------------------------------------------------
  // isDirty
  // -------------------------------------------------------------------------
  describe('isDirty()', () => {
    it('should be false initially after init with empty state', () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      expect(service.isDirty()).toBeFalse();
    });

    it('should become true after addNode()', () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1'));
      expect(service.isDirty()).toBeTrue();
    });

    it('should become true after deleteNode()', () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.deleteNode('n1');
      expect(service.isDirty()).toBeTrue();
    });

    it('should become true after moveNode()', () => {
      const node = makeNode('n1', { x: 0, y: 0 });
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);
      expect(service.isDirty()).toBeTrue();
    });

    it('should remain false after updateNode with identical values', () => {
      const node = makeNode('n1', { x: 10, y: 20 });
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.updateNode('n1', { x: 10, y: 20 }); // same values
      expect(service.isDirty()).toBeFalse();
    });
  });

  // -------------------------------------------------------------------------
  // deleteNode cascade
  // -------------------------------------------------------------------------
  describe('deleteNode()', () => {
    it('should remove the node from localNodes', () => {
      const n1 = makeNode('n1');
      const n2 = makeNode('n2');
      service.initFromBackend({ config_version: 1, nodes: [n1, n2], edges: [] });
      service.deleteNode('n1');
      expect(service.localNodes().map((n) => n.id)).toEqual(['n2']);
    });

    it('should cascade-delete edges where source_node === deleted id', () => {
      const n1 = makeNode('n1');
      const n2 = makeNode('n2');
      const e1 = makeEdge('e1', 'n1', 'n2');
      service.initFromBackend({ config_version: 1, nodes: [n1, n2], edges: [e1] });
      service.deleteNode('n1');
      expect(service.localEdges()).toEqual([]);
    });

    it('should cascade-delete edges where target_node === deleted id', () => {
      const n1 = makeNode('n1');
      const n2 = makeNode('n2');
      const e1 = makeEdge('e1', 'n1', 'n2');
      service.initFromBackend({ config_version: 1, nodes: [n1, n2], edges: [e1] });
      service.deleteNode('n2');
      expect(service.localEdges()).toEqual([]);
    });
  });

  // -------------------------------------------------------------------------
  // addEdge duplicate prevention
  // -------------------------------------------------------------------------
  describe('addEdge()', () => {
    it('should add a new edge', () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addEdge(makeEdge('e1', 'n1', 'n2'));
      expect(service.localEdges().length).toBe(1);
    });

    it('should prevent duplicate edges (same source_node + source_port + target_node)', () => {
      const edge = makeEdge('e1', 'n1', 'n2');
      service.initFromBackend({ config_version: 1, nodes: [], edges: [edge] });
      service.addEdge({ ...edge, id: 'e2' }); // same ports/nodes
      expect(service.localEdges().length).toBe(1);
    });

    it('should assign a temp id if none provided', () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addEdge({ source_node: 'n1', source_port: 'out', target_node: 'n2', target_port: 'in' });
      expect(service.localEdges()[0].id).toMatch(/^__edge__/);
    });
  });

  // -------------------------------------------------------------------------
  // saveAndReload
  // -------------------------------------------------------------------------
  describe('saveAndReload()', () => {
    it('should call dagApi.saveDagConfig() with correct payload', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      await service.saveAndReload();

      expect(dagApiMock.saveDagConfig).toHaveBeenCalledWith(
        jasmine.objectContaining({ base_version: 5 }),
      );
    });

    it('should emit on conflictDetected$ on 409', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.and.returnValue(
        Promise.reject({ status: 409, error: { detail: 'Version conflict' } }),
      );

      const emitted: string[] = [];
      service.conflictDetected$.subscribe((v) => emitted.push(v));

      await service.saveAndReload();

      expect(emitted.length).toBe(1);
      expect(emitted[0]).toContain('Version conflict');
    });

    it('should set isSaving to false after success', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      await service.saveAndReload();

      expect(service.isSaving()).toBeFalse();
    });

    it('should set isSaving to false on error', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.and.returnValue(Promise.reject(new Error('network')));

      await service.saveAndReload();

      expect(service.isSaving()).toBeFalse();
    });

    it('should do nothing when not dirty', async () => {
      service.initFromBackend({ config_version: 5, nodes: [], edges: [] });
      await service.saveAndReload();
      expect(dagApiMock.saveDagConfig).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // syncFromBackend
  // -------------------------------------------------------------------------
  describe('syncFromBackend()', () => {
    it('should call dagApi.getDagConfig() and reset state', async () => {
      const serverNodes = [makeNode('server-n1')];
      dagApiMock.getDagConfig.and.returnValue(
        Promise.resolve({ config_version: 9, nodes: serverNodes, edges: [] }),
      );

      await service.syncFromBackend(true); // skipConfirm=true

      expect(dagApiMock.getDagConfig).toHaveBeenCalled();
      expect(service.localNodes()).toEqual(serverNodes);
      expect(service.baseVersion()).toBe(9);
    });

    it('should skip confirm dialog when not dirty', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      await service.syncFromBackend(); // not dirty, no skipConfirm
      expect(dialogMock.confirm).not.toHaveBeenCalled();
      expect(dagApiMock.getDagConfig).toHaveBeenCalled();
    });

    it('should prompt when dirty and skipConfirm is false', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1')); // make dirty

      dialogMock.confirm.and.returnValue(Promise.resolve(true));
      await service.syncFromBackend();

      expect(dialogMock.confirm).toHaveBeenCalled();
    });

    it('should NOT sync when dirty and user dismisses the prompt', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1')); // make dirty

      dialogMock.confirm.and.returnValue(Promise.resolve(false));
      await service.syncFromBackend();

      expect(dagApiMock.getDagConfig).not.toHaveBeenCalled();
    });

    it('should NOT prompt when skipConfirm=true even if dirty', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1')); // make dirty

      await service.syncFromBackend(true);

      expect(dialogMock.confirm).not.toHaveBeenCalled();
      expect(dagApiMock.getDagConfig).toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // reloadRuntime — critical invariant tests
  // -------------------------------------------------------------------------
  describe('reloadRuntime()', () => {
    it('should call nodesApi.reloadConfig() exactly once', async () => {
      await service.reloadRuntime();
      expect(nodesApiMock.reloadConfig).toHaveBeenCalledTimes(1);
    });

    it('should NOT mutate _localNodes', async () => {
      const node = makeNode('n1');
      service.initFromBackend({ config_version: 3, nodes: [node], edges: [] });
      const before = service.localNodes();

      await service.reloadRuntime();

      expect(service.localNodes()).toEqual(before);
    });

    it('should NOT mutate _localEdges', async () => {
      const edge = makeEdge('e1', 'n1', 'n2');
      service.initFromBackend({ config_version: 3, nodes: [], edges: [edge] });

      await service.reloadRuntime();

      expect(service.localEdges()).toEqual([edge]);
    });

    it('should NOT mutate _baseVersion', async () => {
      service.initFromBackend({ config_version: 42, nodes: [], edges: [] });

      await service.reloadRuntime();

      expect(service.baseVersion()).toBe(42);
    });

    it('should NOT affect isDirty', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1')); // make dirty
      const dirtyBefore = service.isDirty();

      await service.reloadRuntime();

      expect(service.isDirty()).toBe(dirtyBefore);
    });

    it('should set isReloading to true during call and false after success', async () => {
      let wasReloadingDuringCall = false;
      nodesApiMock.reloadConfig.and.callFake(async () => {
        wasReloadingDuringCall = service.isReloading();
        return {};
      });

      await service.reloadRuntime();

      expect(wasReloadingDuringCall).toBeTrue();
      expect(service.isReloading()).toBeFalse();
    });

    it('should set isReloading to false even on error', async () => {
      nodesApiMock.reloadConfig.and.returnValue(Promise.reject(new Error('network error')));

      await service.reloadRuntime();

      expect(service.isReloading()).toBeFalse();
    });

    it('should show success toast on success', async () => {
      await service.reloadRuntime();
      expect(toastMock.success).toHaveBeenCalled();
    });

    it('should show danger toast on error', async () => {
      nodesApiMock.reloadConfig.and.returnValue(
        Promise.reject(new Error('connection refused')),
      );
      await service.reloadRuntime();
      expect(toastMock.danger).toHaveBeenCalled();
    });
  });
});
