import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter, ActivatedRoute} from '@angular/router';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';
import {NodeResultsListComponent} from './node-results-list.component';
import {ResultsApiService} from '@core/services/api/results-api.service';
import {NavigationService} from '@core/services';
import {of} from 'rxjs';
import {ResultSummary} from '@core/models';
import {vi} from 'vitest';

const mockResults: ResultSummary[] = [
  {
    result_id: 'res-001',
    node_id: 'volume_calc_abc123',
    timestamp: 1715000000.0,
    status: 'success',
    metadata_summary: {volume_m3: 12.4, icp_valid: true},
    pcd_count: 3,
  },
  {
    result_id: 'res-002',
    node_id: 'volume_calc_abc123',
    timestamp: 1714990000.0,
    status: 'warning',
    metadata_summary: {volume_m3: 9.1, icp_valid: false},
    pcd_count: 3,
  },
];

describe('NodeResultsListComponent', () => {
  let fixture: ComponentFixture<NodeResultsListComponent>;
  let component: NodeResultsListComponent;
  let apiSpy: {getResultsByNode: ReturnType<typeof vi.fn>};

  beforeEach(async () => {
    apiSpy = {getResultsByNode: vi.fn().mockReturnValue(of(mockResults))};

    await TestBed.configureTestingModule({
      imports: [NodeResultsListComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {provide: ResultsApiService, useValue: apiSpy},
        NavigationService,
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {get: (key: string) => (key === 'nodeId' ? 'volume_calc_abc123' : null)},
            },
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(NodeResultsListComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render result rows in table', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);
  });

  it('should display breadcrumb with Results link', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Results');
  });

  it('should never render raw result_id in the table', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text: string = fixture.nativeElement.textContent;
    expect(text).not.toContain('res-001');
    expect(text).not.toContain('res-002');
    expect(text).not.toContain('volume_calc_abc123');
  });

  it('should show node_name in breadcrumb, not raw nodeId', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // The node 'volume_calc_abc123' is in MOCK_NODE_INDEX as 'Volume Calculation'
    const breadcrumb: HTMLElement = fixture.nativeElement.querySelector('nav');
    expect(breadcrumb?.textContent).not.toContain('volume_calc_abc123');
  });

  it('should show "Unnamed" in breadcrumb when node is not in index', async () => {
    // Override route with unknown nodeId not in MOCK_NODE_INDEX
    await TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [NodeResultsListComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {provide: ResultsApiService, useValue: apiSpy},
        NavigationService,
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {get: (key: string) => (key === 'nodeId' ? 'unknown-id-xyz' : null)},
            },
          },
        },
      ],
    }).compileComponents();
    const f = TestBed.createComponent(NodeResultsListComponent);
    f.detectChanges();
    await f.whenStable();
    f.detectChanges();

    const breadcrumb: HTMLElement = f.nativeElement.querySelector('nav');
    // Must show 'Unnamed', never the raw id
    expect(breadcrumb?.textContent).toContain('Unnamed');
    expect(breadcrumb?.textContent).not.toContain('unknown-id-xyz');
  });

  it('should show empty state message when API returns empty array', async () => {
    apiSpy.getResultsByNode.mockReturnValue(of([]));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('No results');
  });
});
