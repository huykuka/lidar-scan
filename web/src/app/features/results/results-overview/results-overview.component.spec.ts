import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter} from '@angular/router';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';
import {ResultsOverviewComponent} from './results-overview.component';
import {ResultsApiService} from '@core/services/api/results-api.service';
import {NavigationService} from '@core/services';
import {of, throwError} from 'rxjs';
import {NodeResultSummary} from '@core/models';
import {vi} from 'vitest';

const mockNodes: NodeResultSummary[] = [
  {node_id: 'n1', node_name: 'Node 1', node_type: 'volume_calculation', result_count: 5, latest_timestamp: 1715000000},
  {node_id: 'n2', node_name: 'Node 2', node_type: 'vehicle_profiler', result_count: 0, latest_timestamp: null},
];

describe('ResultsOverviewComponent', () => {
  let fixture: ComponentFixture<ResultsOverviewComponent>;
  let component: ResultsOverviewComponent;
  let apiSpy: {getNodeIndex: ReturnType<typeof vi.fn>};

  beforeEach(async () => {
    apiSpy = {getNodeIndex: vi.fn().mockReturnValue(of(mockNodes))};

    await TestBed.configureTestingModule({
      imports: [ResultsOverviewComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {provide: ResultsApiService, useValue: apiSpy},
        NavigationService,
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ResultsOverviewComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display node cards on init', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(apiSpy.getNodeIndex).toHaveBeenCalled();
    expect((component as any).nodes().length).toBe(2);
  });

  it('should show empty state when no nodes returned', async () => {
    apiSpy.getNodeIndex.mockReturnValue(of([]));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('No application nodes');
  });

  it('should fall back to mock data when API errors', async () => {
    apiSpy.getNodeIndex.mockReturnValue(throwError(() => new Error('Network error')));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // Mock fallback has nodes
    expect((component as any).nodes().length).toBeGreaterThan(0);
  });
});
