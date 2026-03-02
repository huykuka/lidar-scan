import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DashboardComponent } from './dashboard.component';
import { MetricsStoreService } from '../../core/services/stores/metrics-store.service';
import { MetricsWebSocketService } from '../../core/services/metrics-websocket.service';
import { MetricsApiService } from '../../core/services/api/metrics-api.service';
import { ComponentPerfService } from '../../core/services/component-perf.service';
import { MetricsMockService } from '../../core/services/mocks/metrics-mock.service';
import { of } from 'rxjs';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';

describe('DashboardComponent', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;
  let mockMetricsStore: jasmine.SpyObj<MetricsStoreService>;
  let mockWebSocketService: jasmine.SpyObj<MetricsWebSocketService>;
  let mockApiService: jasmine.SpyObj<MetricsApiService>;
  let mockPerfService: jasmine.SpyObj<ComponentPerfService>;

  beforeEach(async () => {
    // Create spy objects
    mockMetricsStore = jasmine.createSpyObj('MetricsStoreService', ['update'], {
      isStale: signal(false),
      dagMetrics: signal(null),
      wsMetrics: signal(null),
      systemMetrics: signal(null),
      endpointMetrics: signal(null),
      frontendMetrics: signal(null)
    });

    mockWebSocketService = jasmine.createSpyObj('MetricsWebSocketService', 
      ['connect', 'disconnect'], {
      connected: signal(false)
    });

    mockApiService = jasmine.createSpyObj('MetricsApiService', ['getSnapshot']);
    mockApiService.getSnapshot.and.returnValue(of(null)); // Return observable of null

    mockPerfService = jasmine.createSpyObj('ComponentPerfService', ['startObserving', 'stopObserving']);

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideRouter([]),
        { provide: MetricsStoreService, useValue: mockMetricsStore },
        { provide: MetricsWebSocketService, useValue: mockWebSocketService },
        { provide: MetricsApiService, useValue: mockApiService },
        { provide: ComponentPerfService, useValue: mockPerfService }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
  });

  it('should create without errors', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize services on ngOnInit', () => {
    component.ngOnInit();

    expect(mockWebSocketService.connect).toHaveBeenCalled();
    expect(mockPerfService.startObserving).toHaveBeenCalled();
    expect(mockApiService.getSnapshot).toHaveBeenCalled();
  });

  it('should cleanup services on ngOnDestroy', () => {
    component.ngOnInit();
    component.ngOnDestroy();

    expect(mockWebSocketService.disconnect).toHaveBeenCalled();
    expect(mockPerfService.stopObserving).toHaveBeenCalled();
  });

  it('should show stale banner when isStale is true', () => {
    // Set the store to be stale
    mockMetricsStore.isStale = signal(true);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const staleBanner = compiled.querySelector('[data-testid="stale-banner"]');
    
    expect(staleBanner).toBeTruthy();
    expect(staleBanner?.textContent).toContain('Data stale');
  });

  it('should not show stale banner when isStale is false', () => {
    // Set the store to not be stale
    mockMetricsStore.isStale = signal(false);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const staleBanner = compiled.querySelector('[data-testid="stale-banner"]');
    
    expect(staleBanner).toBeFalsy();
  });
});