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
  const nodesSignal = vi.fn().mockImplementation(() => nodesValue);
  const edgesSignal = vi.fn().mockImplementation(() => edgesValue);
  return {
    nodes: nodesSignal,
    edges: edgesSignal,
    nodeDefinitions: vi.fn().mockReturnValue([]),
    setState: vi.fn().mockImplementation((state: any) => {
      if (state.nodes !== undefined) nodesValue = state.nodes;
      if (state.edges !== undefined) edgesValue = state.edges;
    }),
    _setNodes: (n: NodeConfig[]) => { nodesValue = n; },
    _setEdges: (e: Edge[]) => { edgesValue = e; },
  };
}

function createDagApiMock() {
  return {
    getDagConfig: vi.fn().mockResolvedValue(
      { config_version: 5, nodes: [], edges: [] } as DagConfigResponse,
    ),
    saveDagConfig: vi.fn().mockResolvedValue(
      { config_version: 6, node_id_map: {} },
    ),
  };
}

function createToastMock() {
  return {
    success: vi.fn(),
    danger: vi.fn(),
    warning: vi.fn(),
  };
}

function createDialogMock() {
  return {
    confirm: vi.fn().mockResolvedValue(true),
  };
}

function createNodesApiMock() {
  return {
    reloadConfig: vi.fn().mockResolvedValue({}),
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
      expect(service.isDirty()).toBe(false);
    });

    it('should become true after addNode()', () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1'));
      expect(service.isDirty()).toBe(true);
    });

    it('should become true after deleteNode()', () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.deleteNode('n1');
      expect(service.isDirty()).toBe(true);
    });

    it('should become true after moveNode()', () => {
      const node = makeNode('n1', { x: 0, y: 0 });
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);
      expect(service.isDirty()).toBe(true);
    });

    it('should remain false after updateNode with identical values', () => {
      const node = makeNode('n1', { x: 10, y: 20 });
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 1, nodes: [node], edges: [] });
      service.updateNode('n1', { x: 10, y: 20 }); // same values
      expect(service.isDirty()).toBe(false);
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
        expect.objectContaining({ base_version: 5 }),
      );
    });

    it('should emit on conflictDetected$ on 409', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.mockRejectedValueOnce(
        { status: 409, error: { detail: 'Version conflict' } },
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

      expect(service.isSaving()).toBe(false);
    });

    it('should set isSaving to false on error', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.mockRejectedValueOnce(new Error('network'));

      await service.saveAndReload();

      expect(service.isSaving()).toBe(false);
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
      dagApiMock.getDagConfig.mockResolvedValueOnce(
        { config_version: 9, nodes: serverNodes, edges: [] },
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

      dialogMock.confirm.mockResolvedValueOnce(true);
      await service.syncFromBackend();

      expect(dialogMock.confirm).toHaveBeenCalled();
    });

    it('should NOT sync when dirty and user dismisses the prompt', async () => {
      service.initFromBackend({ config_version: 1, nodes: [], edges: [] });
      service.addNode(makeNode('n1')); // make dirty

      dialogMock.confirm.mockResolvedValueOnce(false);
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
      nodesApiMock.reloadConfig.mockImplementationOnce(async () => {
        wasReloadingDuringCall = service.isReloading();
        return {};
      });

      await service.reloadRuntime();

      expect(wasReloadingDuringCall).toBe(true);
      expect(service.isReloading()).toBe(false);
    });

    it('should set isReloading to false even on error', async () => {
      nodesApiMock.reloadConfig.mockRejectedValueOnce(new Error('network error'));

      await service.reloadRuntime();

      expect(service.isReloading()).toBe(false);
    });

    it('should show success toast on success', async () => {
      await service.reloadRuntime();
      expect(toastMock.success).toHaveBeenCalled();
    });

    it('should show danger toast on error', async () => {
      nodesApiMock.reloadConfig.mockRejectedValueOnce(
        new Error('connection refused'),
      );
      await service.reloadRuntime();
      expect(toastMock.danger).toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // saveAndReload debounce (Phase 4.1)
  // -------------------------------------------------------------------------
  describe('saveAndReload() — 150ms debounce', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should debounce rapid consecutive calls and issue only one HTTP request', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      // Call saveAndReload three times rapidly — don't await intermediate calls.
      // Each new call cancels the previous timer; only the last one fires.
      service.saveAndReload(); // fire-and-forget (p1 will never resolve as it's pre-empted)
      service.saveAndReload(); // fire-and-forget (p2 will never resolve as it's pre-empted)
      const p3 = service.saveAndReload(); // last call — this one fires

      // Advance timers past the debounce threshold so the last queued save executes
      await vi.runAllTimersAsync();
      await p3;

      // Only one HTTP call should have been made
      expect(dagApiMock.saveDagConfig).toHaveBeenCalledTimes(1);
    });

    it('should still call saveDagConfig after the 150ms debounce window', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(dagApiMock.saveDagConfig).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // saveAndReload 409 handling (Phase 4.2)
  // -------------------------------------------------------------------------
  describe('saveAndReload() — 409 error handling', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should emit on conflictDetected$ for version-conflict 409', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.mockRejectedValueOnce({
        status: 409,
        error: { detail: 'Version conflict — base_version is stale' },
      });

      const emitted: string[] = [];
      service.conflictDetected$.subscribe((v) => emitted.push(v));

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(emitted.length).toBe(1);
      expect(emitted[0].toLowerCase()).toContain('version conflict');
    });

    it('should show warning toast for lock-conflict 409 (reload already in progress)', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 999, 888);

      dagApiMock.saveDagConfig.mockRejectedValueOnce({
        status: 409,
        error: { detail: 'Reload is already in progress. Please wait.' },
      });

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(toastMock.warning).toHaveBeenCalled();
      expect(toastMock.warning.mock.calls[0][0]).toContain('reload is already in progress');
    });
  });

  // -------------------------------------------------------------------------
  // saveAndReload toast messages based on reload_mode (Phase 4.3)
  // -------------------------------------------------------------------------
  describe('saveAndReload() — reload_mode toast messages', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should show selective toast when reload_mode is "selective"', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);

      dagApiMock.saveDagConfig.mockResolvedValueOnce({
        config_version: 6,
        node_id_map: {},
        reload_mode: 'selective',
        reloaded_node_ids: ['n1', 'n2'],
      });

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(toastMock.success).toHaveBeenCalled();
      const msg: string = toastMock.success.mock.calls[0][0];
      expect(msg.toLowerCase()).toContain('2 node');
    });

    it('should show full-reload toast when reload_mode is "full"', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);

      dagApiMock.saveDagConfig.mockResolvedValueOnce({
        config_version: 6,
        node_id_map: {},
        reload_mode: 'full',
        reloaded_node_ids: [],
      });

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(toastMock.success).toHaveBeenCalled();
      const msg: string = toastMock.success.mock.calls[0][0];
      expect(msg.toLowerCase()).toContain('reloading dag');
    });

    it('should show generic saved toast when reload_mode is "none"', async () => {
      const node = makeNode('n1');
      nodeStoreMock._setNodes([node]);
      service.initFromBackend({ config_version: 5, nodes: [node], edges: [] });
      service.moveNode('n1', 100, 200);

      dagApiMock.saveDagConfig.mockResolvedValueOnce({
        config_version: 6,
        node_id_map: {},
        reload_mode: 'none',
        reloaded_node_ids: [],
      });

      const p = service.saveAndReload();
      await vi.runAllTimersAsync();
      await p;

      expect(toastMock.success).toHaveBeenCalled();
      const msg: string = toastMock.success.mock.calls[0][0];
      expect(msg.toLowerCase()).toContain('saved');
    });
  });
});
