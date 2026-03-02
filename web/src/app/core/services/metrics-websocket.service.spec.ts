import { TestBed } from '@angular/core/testing';
import { MetricsWebSocketService } from './metrics-websocket.service';
import { MetricsStoreService } from './stores/metrics-store.service';
import { MOCK_METRICS_SNAPSHOT } from './mocks/metrics-mock.service';

// Mock WebSocket
class MockWebSocket {
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  binaryType = 'text';
  
  constructor(public url: string) {}
  
  close() {
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }
  
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
    }
  }
  
  simulateOpen() {
    if (this.onopen) {
      this.onopen(new Event('open'));
    }
  }
  
  simulateClose() {
    if (this.onclose) {
      this.onclose(new CloseEvent('close'));
    }
  }
}

describe('MetricsWebSocketService', () => {
  let service: MetricsWebSocketService;
  let metricsStore: jasmine.SpyObj<MetricsStoreService>;
  let mockWebSocket: MockWebSocket;

  beforeEach(() => {
    const metricsStoreSpy = jasmine.createSpyObj('MetricsStoreService', ['update', 'markStale']);

    TestBed.configureTestingModule({
      providers: [
        { provide: MetricsStoreService, useValue: metricsStoreSpy }
      ]
    });
    
    service = TestBed.inject(MetricsWebSocketService);
    metricsStore = TestBed.inject(MetricsStoreService) as jasmine.SpyObj<MetricsStoreService>;

    // Mock global WebSocket
    spyOn(window, 'WebSocket').and.callFake((url: string) => {
      mockWebSocket = new MockWebSocket(url);
      return mockWebSocket as any;
    });
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should set connected to false initially', () => {
    expect(service.connected()).toBe(false);
  });

  it('should parse valid MetricsSnapshot and call store.update()', () => {
    service.connect();
    
    // Simulate connection open
    mockWebSocket.simulateOpen();
    expect(service.connected()).toBe(true);
    
    // Simulate message with valid data
    mockWebSocket.simulateMessage(MOCK_METRICS_SNAPSHOT);
    
    expect(metricsStore.update).toHaveBeenCalledWith(MOCK_METRICS_SNAPSHOT);
  });

  it('should call store.markStale() on disconnect', () => {
    service.connect();
    mockWebSocket.simulateOpen();
    
    // Simulate disconnect
    mockWebSocket.simulateClose();
    
    expect(service.connected()).toBe(false);
    expect(metricsStore.markStale).toHaveBeenCalled();
  });

  it('should disconnect properly', () => {
    service.connect();
    mockWebSocket.simulateOpen();
    
    spyOn(mockWebSocket, 'close');
    
    service.disconnect();
    expect(mockWebSocket.close).toHaveBeenCalled();
  });
});