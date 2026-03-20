import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { StatusWebSocketService } from './status-websocket.service';
import { NodesStatusResponse, NodeStatusUpdate } from '../models/node-status.model';

describe('StatusWebSocketService', () => {
  let service: StatusWebSocketService;
  let mockWebSocket: any;
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    // Save original WebSocket
    originalWebSocket = (globalThis as any).WebSocket;

    // Mock WebSocket
    mockWebSocket = {
      readyState: WebSocket.CONNECTING,
      send: jasmine.createSpy('send'),
      close: jasmine.createSpy('close'),
      onopen: null,
      onmessage: null,
      onerror: null,
      onclose: null,
    };

    (globalThis as any).WebSocket = jasmine.createSpy('WebSocket').and.returnValue(mockWebSocket);

    TestBed.configureTestingModule({
      providers: [StatusWebSocketService],
    });
    service = TestBed.inject(StatusWebSocketService);
  });

  afterEach(() => {
    // Restore original WebSocket
    (globalThis as any).WebSocket = originalWebSocket;
    service.disconnect();
  });

  it('should parse NodeStatusUpdate array from a WebSocket JSON message', fakeAsync(() => {
    service.connect();
    mockWebSocket.readyState = WebSocket.OPEN;

    const mockPayload: NodesStatusResponse = {
      nodes: [
        {
          node_id: 'test_node_1',
          operational_state: 'RUNNING',
          application_state: { label: 'test', value: 'active', color: 'green' },
          timestamp: Date.now() / 1000,
        },
      ],
    };

    // Simulate WebSocket message
    const messageEvent = { data: JSON.stringify(mockPayload) } as MessageEvent;
    mockWebSocket.onmessage(messageEvent);

    // Wait for debounce (50ms)
    tick(50);

    const status = service.status();
    expect(status).toBeTruthy();
    expect(status?.nodes.length).toBe(1);
    expect(status?.nodes[0].node_id).toBe('test_node_1');
    expect(status?.nodes[0].operational_state).toBe('RUNNING');
  }));

  it('should debounce rapid messages and update signal only once within the 50ms window', fakeAsync(() => {
    service.connect();
    mockWebSocket.readyState = WebSocket.OPEN;

    const payload1: NodesStatusResponse = {
      nodes: [{ node_id: 'node_1', operational_state: 'INITIALIZE', timestamp: Date.now() / 1000 }],
    };
    const payload2: NodesStatusResponse = {
      nodes: [{ node_id: 'node_1', operational_state: 'RUNNING', timestamp: Date.now() / 1000 }],
    };
    const payload3: NodesStatusResponse = {
      nodes: [{ node_id: 'node_1', operational_state: 'ERROR', timestamp: Date.now() / 1000 }],
    };

    // Send three rapid messages
    mockWebSocket.onmessage({ data: JSON.stringify(payload1) } as MessageEvent);
    tick(10);
    mockWebSocket.onmessage({ data: JSON.stringify(payload2) } as MessageEvent);
    tick(10);
    mockWebSocket.onmessage({ data: JSON.stringify(payload3) } as MessageEvent);

    // Before debounce completes, status should still be null
    expect(service.status()).toBeNull();

    // After debounce completes (50ms total)
    tick(30);

    const status = service.status();
    expect(status).toBeTruthy();
    // Should have the LAST message (payload3)
    expect(status?.nodes[0].operational_state).toBe('ERROR');
  }));

  it('should allow multiple debounce windows to fire separately', fakeAsync(() => {
    service.connect();
    mockWebSocket.readyState = WebSocket.OPEN;

    const payload1: NodesStatusResponse = {
      nodes: [{ node_id: 'node_1', operational_state: 'INITIALIZE', timestamp: Date.now() / 1000 }],
    };
    const payload2: NodesStatusResponse = {
      nodes: [{ node_id: 'node_1', operational_state: 'RUNNING', timestamp: Date.now() / 1000 }],
    };

    // First message
    mockWebSocket.onmessage({ data: JSON.stringify(payload1) } as MessageEvent);
    tick(50);
    expect(service.status()?.nodes[0].operational_state).toBe('INITIALIZE');

    // Second message after debounce window
    tick(60); // Wait well past debounce
    mockWebSocket.onmessage({ data: JSON.stringify(payload2) } as MessageEvent);
    tick(50);
    expect(service.status()?.nodes[0].operational_state).toBe('RUNNING');
  }));
});
