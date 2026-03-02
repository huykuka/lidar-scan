import { TestBed } from '@angular/core/testing';
import { MetricsStoreService } from './metrics-store.service';
import { MOCK_METRICS_SNAPSHOT } from '../mocks/metrics-mock.service';

describe('MetricsStoreService', () => {
  let service: MetricsStoreService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(MetricsStoreService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should initialize with null signals', () => {
    expect(service.dagMetrics()).toBeNull();
    expect(service.wsMetrics()).toBeNull();
    expect(service.systemMetrics()).toBeNull();
    expect(service.endpointMetrics()).toBeNull();
    expect(service.frontendMetrics()).toBeNull();
    expect(service.lastUpdatedAt()).toBeNull();
    expect(service.isStale()).toBe(false);
  });

  it('should update dagMetrics on update()', () => {
    service.update(MOCK_METRICS_SNAPSHOT);
    
    expect(service.dagMetrics()).toEqual(MOCK_METRICS_SNAPSHOT.dag);
    expect(service.wsMetrics()).toEqual(MOCK_METRICS_SNAPSHOT.websocket);
    expect(service.systemMetrics()).toEqual(MOCK_METRICS_SNAPSHOT.system);
    expect(service.endpointMetrics()).toEqual(MOCK_METRICS_SNAPSHOT.endpoints);
    expect(service.lastUpdatedAt()).toBeCloseTo(Date.now(), -2); // Within 100ms
    expect(service.isStale()).toBe(false);
  });

  it('should compute totalPointsPerSec correctly', () => {
    service.update(MOCK_METRICS_SNAPSHOT);
    
    // From mock data: node1 has 1234.5, node2 has 987.6
    const expected = 1234.5 + 987.6;
    expect(service.totalPointsPerSec()).toBe(expected);
  });

  it('should compute worstNodeLatencyMs correctly', () => {
    service.update(MOCK_METRICS_SNAPSHOT);
    
    // From mock data: node1 has 2.4, node2 has 1.8
    const expected = Math.max(2.4, 1.8);
    expect(service.worstNodeLatencyMs()).toBe(expected);
  });

  it('should compute activeNodeCount correctly', () => {
    service.update(MOCK_METRICS_SNAPSHOT);
    
    expect(service.activeNodeCount()).toBe(MOCK_METRICS_SNAPSHOT.dag.running_nodes);
  });

  it('should mark stale', () => {
    // Initially not stale
    expect(service.isStale()).toBe(false);
    
    // Mark as stale
    service.markStale();
    expect(service.isStale()).toBe(true);
    
    // Update should reset stale flag
    service.update(MOCK_METRICS_SNAPSHOT);
    expect(service.isStale()).toBe(false);
  });
});