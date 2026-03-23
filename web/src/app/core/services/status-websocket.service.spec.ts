// @ts-nocheck
import {TestBed} from '@angular/core/testing';
import {StatusWebSocketService} from './status-websocket.service';
import {NodesStatusResponse} from '../models/node-status.model';

describe('StatusWebSocketService', () => {
  let service: StatusWebSocketService;
  let capturedOnmessage: ((event: MessageEvent) => void) | null = null;
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    vi.useFakeTimers();

    // Save original WebSocket
    originalWebSocket = (globalThis as any).WebSocket;

    capturedOnmessage = null;

    // Mock WebSocket constructor using a proper function (not arrow fn) so `new` works
    function MockWS(this: any, _url: string) {
      this.readyState = 0; // CONNECTING
      this.send = vi.fn();
      this.close = vi.fn();
      this.onopen = null;
      this.onerror = null;
      this.onclose = null;

      Object.defineProperty(this, 'onmessage', {
        set(handler: any) {
          capturedOnmessage = handler;
        },
        get() {
          return capturedOnmessage;
        },
        configurable: true,
      });
    }

    // Copy static constants
    (MockWS as any).CONNECTING = 0;
    (MockWS as any).OPEN = 1;
    (MockWS as any).CLOSING = 2;
    (MockWS as any).CLOSED = 3;

    (globalThis as any).WebSocket = MockWS;

    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [StatusWebSocketService],
    });
    service = TestBed.inject(StatusWebSocketService);
  });

  afterEach(() => {
    vi.useRealTimers();
    // Restore original WebSocket
    (globalThis as any).WebSocket = originalWebSocket;
    service.disconnect();
  });

  it('should parse NodeStatusUpdate array from a WebSocket JSON message', () => {
    service.connect();

    const mockPayload: NodesStatusResponse = {
      nodes: [
        {
          node_id: 'test_node_1',
          operational_state: 'RUNNING',
          application_state: {label: 'test', value: 'active', color: 'green'},
          timestamp: Date.now() / 1000,
        },
      ],
    };

    // Simulate WebSocket message via the captured handler
    expect(capturedOnmessage).not.toBeNull();
    const messageEvent = {data: JSON.stringify(mockPayload)} as MessageEvent;
    capturedOnmessage!(messageEvent);

    // Before debounce fires, status should still be null
    expect(service.status()).toBeNull();

    // Wait for debounce (50ms)
    vi.advanceTimersByTime(50);

    const status = service.status();
    expect(status).toBeTruthy();
    expect(status?.nodes.length).toBe(1);
    expect(status?.nodes[0].node_id).toBe('test_node_1');
    expect(status?.nodes[0].operational_state).toBe('RUNNING');
  });

  it('should debounce rapid messages and update signal only once within the 50ms window', () => {
    service.connect();

    const payload1: NodesStatusResponse = {
      nodes: [{node_id: 'node_1', operational_state: 'INITIALIZE', timestamp: Date.now() / 1000}],
    };
    const payload2: NodesStatusResponse = {
      nodes: [{node_id: 'node_1', operational_state: 'RUNNING', timestamp: Date.now() / 1000}],
    };
    const payload3: NodesStatusResponse = {
      nodes: [{node_id: 'node_1', operational_state: 'ERROR', timestamp: Date.now() / 1000}],
    };

    expect(capturedOnmessage).not.toBeNull();

    // Send three rapid messages
    capturedOnmessage!({data: JSON.stringify(payload1)} as MessageEvent);
    vi.advanceTimersByTime(10);
    capturedOnmessage!({data: JSON.stringify(payload2)} as MessageEvent);
    vi.advanceTimersByTime(10);
    capturedOnmessage!({data: JSON.stringify(payload3)} as MessageEvent);

    // Before debounce completes, status should still be null
    expect(service.status()).toBeNull();

    // After debounce completes (50ms total)
    vi.advanceTimersByTime(30);

    const status = service.status();
    expect(status).toBeTruthy();
    // Should have the LAST message (payload3)
    expect(status?.nodes[0].operational_state).toBe('ERROR');
  });

  it('should allow multiple debounce windows to fire separately', () => {
    service.connect();

    const payload1: NodesStatusResponse = {
      nodes: [{node_id: 'node_1', operational_state: 'INITIALIZE', timestamp: Date.now() / 1000}],
    };
    const payload2: NodesStatusResponse = {
      nodes: [{node_id: 'node_1', operational_state: 'RUNNING', timestamp: Date.now() / 1000}],
    };

    expect(capturedOnmessage).not.toBeNull();

    // First message
    capturedOnmessage!({data: JSON.stringify(payload1)} as MessageEvent);
    vi.advanceTimersByTime(50);
    expect(service.status()?.nodes[0].operational_state).toBe('INITIALIZE');

    // Second message after debounce window
    vi.advanceTimersByTime(60); // Wait well past debounce
    capturedOnmessage!({data: JSON.stringify(payload2)} as MessageEvent);
    vi.advanceTimersByTime(50);
    expect(service.status()?.nodes[0].operational_state).toBe('RUNNING');
  });
});
