// @ts-nocheck
import {TestBed, fakeAsync, tick} from '@angular/core/testing';
import {CUSTOM_ELEMENTS_SCHEMA} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {Subject} from 'rxjs';
import {OutputNodeComponent} from './output-node.component';
import {MultiWebsocketService} from '@core/services/multi-websocket.service';
import {OutputNodeApiService} from '@features/output-node/services/output-node-api.service';
import {
  MOCK_OUTPUT_NODE,
  MOCK_WEBHOOK_CONFIG_DISABLED,
} from '@core/mocks/output-node-api.mock';

/**
 * Unit tests for OutputNodeComponent (smart container).
 *
 * TDD tests covering F4.6 specs:
 *   - 404 node not found
 *   - Connecting status initially
 *   - Connected after first WS message
 *   - Disconnected on WS error
 *   - Passes filtered metadata
 *   - Ignores messages from different node_id
 *   - Unsubscribes on destroy
 */
describe('OutputNodeComponent', () => {
  const TEST_NODE_ID = 'test-node-abc123';

  let wsSubject: Subject<string>;
  let mockWsService: {
    connect: ReturnType<typeof vi.fn>;
    disconnect: ReturnType<typeof vi.fn>;
    getActiveTopics: ReturnType<typeof vi.fn>;
    isConnected: ReturnType<typeof vi.fn>;
  };
  let mockApiService: ReturnType<typeof vi.fn>;
  let mockRouter: {navigate: ReturnType<typeof vi.fn>};

  function makeMetadataMessage(nodeId: string, metadata: Record<string, any> = {}): string {
    return JSON.stringify({
      type: 'output_node_metadata',
      node_id: nodeId,
      timestamp: Date.now() / 1000,
      metadata: {point_count: 1000, ...metadata},
    });
  }

  function makeOtherMessage(): string {
    return JSON.stringify({
      type: 'node_status',
      node_id: TEST_NODE_ID,
      status: 'running',
    });
  }

  beforeEach(async () => {
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    wsSubject = new Subject<string>();

    mockWsService = {
      connect: vi.fn().mockReturnValue(wsSubject.asObservable()),
      disconnect: vi.fn(),
      getActiveTopics: vi.fn().mockReturnValue(['system_status']),
      isConnected: vi.fn().mockReturnValue(true),
    };

    mockApiService = {
      getNode: vi.fn().mockResolvedValue(MOCK_OUTPUT_NODE),
      getWebhookConfig: vi.fn().mockResolvedValue(MOCK_WEBHOOK_CONFIG_DISABLED),
      updateWebhookConfig: vi.fn().mockResolvedValue({status: 'ok', node_id: TEST_NODE_ID}),
    };

    mockRouter = {navigate: vi.fn()};

    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [OutputNodeComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {params: {nodeId: TEST_NODE_ID}},
          },
        },
        {provide: Router, useValue: mockRouter},
        {provide: MultiWebsocketService, useValue: mockWsService},
        {provide: OutputNodeApiService, useValue: mockApiService},
      ],
    }).compileComponents();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-1: Shows 404 error when node not found
  // ──────────────────────────────────────────────────────────────────────────

  it('shows 404 error when node not found', async () => {
    mockApiService.getNode.mockRejectedValue({status: 404});

    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.nodeNotFound()).toBe(true);

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.textContent).toContain('Node Not Found');
  });

  it('does not connect WebSocket when node returns 404', async () => {
    mockApiService.getNode.mockRejectedValue({status: 404});

    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(mockWsService.connect).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-2: Shows connecting status initially
  // ──────────────────────────────────────────────────────────────────────────

  it('shows connecting status initially (before WS messages arrive)', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.connectionStatus()).toBe('connecting');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-3: Shows connected status after first WS message
  // ──────────────────────────────────────────────────────────────────────────

  it('shows connected status after first WS message', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Flush microtasks from async ngOnInit (two sequential awaits) so wsSub is assigned
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    wsSubject.next(makeMetadataMessage(TEST_NODE_ID));
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.connectionStatus()).toBe('connected');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-4: Shows disconnected status on WS error
  // ──────────────────────────────────────────────────────────────────────────

  it('shows disconnected status on WS error', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Flush microtasks from async ngOnInit so wsSub is assigned
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    wsSubject.error(new Error('Connection refused'));
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.connectionStatus()).toBe('disconnected');
  });

  it('shows disconnected status when WS completes', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Flush microtasks from async ngOnInit so wsSub is assigned
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    wsSubject.complete();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.connectionStatus()).toBe('disconnected');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-5: Passes filtered metadata to metadata-table
  // ──────────────────────────────────────────────────────────────────────────

  it('passes filtered metadata to metadata-table', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Flush microtasks from async ngOnInit so wsSub is assigned
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    const testMetadata = {point_count: 45000, sensor_name: 'lidar_front'};
    wsSubject.next(makeMetadataMessage(TEST_NODE_ID, testMetadata));
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.metadata()).toEqual(expect.objectContaining(testMetadata));
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-6: Ignores WS messages from different node_id
  // ──────────────────────────────────────────────────────────────────────────

  it('ignores WS messages from different node_id', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // Send message for a DIFFERENT node
    wsSubject.next(makeMetadataMessage('other-node-xyz', {point_count: 99999}));
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    // metadata should remain null
    expect(comp.metadata()).toBeNull();
    // status should remain connecting
    expect(comp.connectionStatus()).toBe('connecting');
  });

  it('ignores non-output_node_metadata message types', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    wsSubject.next(makeOtherMessage());
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.metadata()).toBeNull();
  });

  it('ignores malformed JSON messages without throwing', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // Should not throw
    wsSubject.next('not-valid-json{{{');
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.metadata()).toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // F4.6-7: Unsubscribes on destroy
  // ──────────────────────────────────────────────────────────────────────────

  it('unsubscribes from WS on destroy', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Flush microtasks from async ngOnInit so wsSub is assigned
    await Promise.resolve();
    await Promise.resolve();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.wsSub).toBeDefined();
    const unsubSpy = vi.spyOn(comp.wsSub, 'unsubscribe');

    fixture.destroy();

    expect(unsubSpy).toHaveBeenCalled();
  });

  it('does NOT call wsService.disconnect on destroy (shared topic)', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.destroy();

    expect(mockWsService.disconnect).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Node name loading
  // ──────────────────────────────────────────────────────────────────────────

  it('sets nodeName from API response', async () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    expect(comp.nodeName()).toBe(MOCK_OUTPUT_NODE.name);
  });

  it('uses nodeId as fallback name on non-404 API error', async () => {
    mockApiService.getNode.mockRejectedValue({status: 500});

    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    // Extra cycle so all async effects (including WS connect) complete
    fixture.detectChanges();
    await fixture.whenStable();

    const comp = fixture.componentInstance as any;
    expect(comp.nodeNotFound()).toBe(false);
    expect(comp.nodeName()).toBe(TEST_NODE_ID);
    // Should still connect to WS
    expect(mockWsService.connect).toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // goBack navigation
  // ──────────────────────────────────────────────────────────────────────────

  it('navigates to /settings on goBack', () => {
    const fixture = TestBed.createComponent(OutputNodeComponent);
    fixture.detectChanges();

    const comp = fixture.componentInstance as any;
    comp.goBack();

    expect(mockRouter.navigate).toHaveBeenCalledWith(['/settings']);
  });
});
