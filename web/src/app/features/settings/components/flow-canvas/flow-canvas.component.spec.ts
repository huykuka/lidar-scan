import {signal} from '@angular/core';
import {TestBed} from '@angular/core/testing';

import {FlowCanvasComponent} from './flow-canvas.component';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';
import {NodePluginRegistry} from '@core/services/node-plugin-registry.service';
import {NodeStatusService} from '@core/services/node-status.service';
import {NodesApiService} from '@core/services/api/nodes-api.service';
import {ToastService} from '@core/services/toast.service';
import {DialogService} from '@core/services/dialog.service';
import {NodeDefinition} from '@core/models/node.model';
import {NodePlugin} from '@core/models';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const makeMockDefinition = (type = 'sensor'): NodeDefinition => ({
  type,
  category: type,
  display_name: `Mock ${type}`,
  description: '',
  icon: 'sensors',
  websocket_enabled: true,
  inputs: [],
  outputs: [],
  properties: [],
});

const makeMockPlugin = (type = 'sensor'): NodePlugin => ({
  type,
  category: type,
  displayName: `Mock ${type}`,
  description: '',
  icon: 'sensors',
  style: {color: '#10b981'},
  ports: {inputs: [], outputs: []},
  createInstance: () => ({type, category: type, name: 'Mock', enabled: true, config: {}}),
  renderBody: () => ({fields: []}),
});

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

function createNodeStoreMock(definitions: NodeDefinition[] = []) {
  const nodeDefsSignal = signal<NodeDefinition[]>(definitions);
  return {
    nodes: signal([]),
    edges: signal([]),
    nodeDefinitions: nodeDefsSignal.asReadonly(),
    _setDefinitions: (defs: NodeDefinition[]) => nodeDefsSignal.set(defs),
    nodeStatusMap: signal(new Map()),
    set: vi.fn(),
    setState: vi.fn(),
  };
}

function createCanvasEditStoreMock() {
  return {
    localNodes: signal([]),
    localEdges: signal([]),
    isDirty: signal(false),
    isValid: signal(true),
    validationErrors: signal([]),
    isSaving: signal(false),
    isSyncing: signal(false),
    isReloading: signal(false),
    addEdge: vi.fn(),
    deleteEdge: vi.fn(),
    deleteNode: vi.fn(),
    moveNode: vi.fn(),
    updateNode: vi.fn(),
    addNode: vi.fn(),
  };
}

function createPluginRegistryMock(plugins: NodePlugin[] = []) {
  return {
    loadFromBackend: vi.fn().mockResolvedValue(undefined),
    getAll: vi.fn().mockReturnValue(plugins),
    get: vi.fn().mockReturnValue(undefined),
  };
}

function createStatusWsMock() {
  return {
    status: signal(null),
    connected: signal(false),
    connect: vi.fn(),
    disconnect: vi.fn(),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FlowCanvasComponent — initialization', () => {
  // The component uses many Synergy web components — suppress the
  // CUSTOM_ELEMENTS_SCHEMA errors by polyfilling getAnimations.
  beforeEach(() => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }
  });

  it('should be created', async () => {
    const nodeStoreMock = createNodeStoreMock();
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock();
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('isPaletteLoading starts as true before definitions are loaded', async () => {
    const nodeStoreMock = createNodeStoreMock([]); // empty definitions initially
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock([]);
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.isPaletteLoading()).toBe(true);
  });

  it('availablePlugins is empty before definitions are loaded', async () => {
    const nodeStoreMock = createNodeStoreMock([]); // no definitions
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock([]);
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.availablePlugins()).toEqual([]);
  });

  it('isPaletteLoading becomes false when nodeDefinitions are populated', async () => {
    const mockDef = makeMockDefinition('sensor');
    const mockPlugin = makeMockPlugin('sensor');

    const nodeStoreMock = createNodeStoreMock([]); // starts empty
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock([mockPlugin]);
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.isPaletteLoading()).toBe(true);

    // Simulate definitions being loaded (as if NodePluginRegistry.loadFromBackend() completed)
    nodeStoreMock._setDefinitions([mockDef]);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(comp.isPaletteLoading()).toBe(false);
  });

  it('availablePlugins is populated when nodeDefinitions are set', async () => {
    const mockDef = makeMockDefinition('sensor');
    const mockPlugin = makeMockPlugin('sensor');

    const nodeStoreMock = createNodeStoreMock([]); // starts empty
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock([mockPlugin]);
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();

    // Simulate backend load completing: definitions appear in store
    nodeStoreMock._setDefinitions([mockDef]);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.availablePlugins()).toEqual([mockPlugin]);
    expect(pluginRegistryMock.getAll).toHaveBeenCalled();
  });

  it('connects to WebSocket on init', async () => {
    const nodeStoreMock = createNodeStoreMock();
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock();
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();

    expect(statusWsMock.connect).toHaveBeenCalledTimes(1);
  });

  it('disconnects from WebSocket on destroy', async () => {
    const nodeStoreMock = createNodeStoreMock();
    const canvasEditStoreMock = createCanvasEditStoreMock();
    const pluginRegistryMock = createPluginRegistryMock();
    const statusWsMock = createStatusWsMock();

    await TestBed.configureTestingModule({
      imports: [FlowCanvasComponent],
      providers: [
        {provide: NodeStoreService, useValue: nodeStoreMock},
        {provide: CanvasEditStoreService, useValue: canvasEditStoreMock},
        {provide: NodePluginRegistry, useValue: pluginRegistryMock},
        {provide: NodeStatusService, useValue: statusWsMock},
        {provide: NodesApiService, useValue: {setNodeEnabled: vi.fn(), setNodeVisible: vi.fn()}},
        {provide: ToastService, useValue: {success: vi.fn(), danger: vi.fn(), warning: vi.fn()}},
        {provide: DialogService, useValue: {confirm: vi.fn().mockResolvedValue(true)}},
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(FlowCanvasComponent);
    fixture.detectChanges();
    fixture.destroy();

    expect(statusWsMock.disconnect).toHaveBeenCalledTimes(1);
  });
});
