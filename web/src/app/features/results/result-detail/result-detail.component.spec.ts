import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter, ActivatedRoute} from '@angular/router';
import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';
import {ResultDetailComponent} from './result-detail.component';
import {ResultsApiService} from '@core/services/api/results-api.service';
import {NavigationService} from '@core/services';
import {of, throwError} from 'rxjs';
import {ResultDetail} from '@core/models';
import {PcdParserService} from '@core/services/pcd-parser.service';
import {vi} from 'vitest';

const mockDetail: ResultDetail = {
  result_id: '550e8400-e29b-41d4-a716-446655440000',
  node_id: 'volume_calc_abc123',
  timestamp: 1715000000.123,
  status: 'success',
  metadata: {volume_m3: 12.4, icp_valid: true, cell_count: 2048},
  pcd_files: [
    {label: 'empty', url: '/api/v1/results/volume_calc_abc123/550e8400.../pcd/empty'},
    {label: 'loaded', url: '/api/v1/results/volume_calc_abc123/550e8400.../pcd/loaded'},
  ],
};

// Minimal WebGL mock
beforeAll(() => {
  (HTMLCanvasElement.prototype as any).getContext = () => ({
    getExtension: () => null,
    getParameter: () => null,
    createBuffer: () => ({}),
    bindBuffer: () => {},
    bufferData: () => {},
    enable: () => {},
    disable: () => {},
    clearColor: () => {},
    clear: () => {},
    viewport: () => {},
    isContextLost: () => false,
  });
});

describe('ResultDetailComponent', () => {
  let fixture: ComponentFixture<ResultDetailComponent>;
  let component: ResultDetailComponent;
  let apiSpy: {getResultDetail: ReturnType<typeof vi.fn>};

  beforeEach(async () => {
    apiSpy = {getResultDetail: vi.fn().mockReturnValue(of(mockDetail))};

    await TestBed.configureTestingModule({
      imports: [ResultDetailComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {provide: ResultsApiService, useValue: apiSpy},
        NavigationService,
        PcdParserService,
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (key: string) => {
                  if (key === 'nodeId') return 'volume_calc_abc123';
                  if (key === 'resultId') return '550e8400-e29b-41d4-a716-446655440000';
                  return null;
                },
              },
            },
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ResultDetailComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should load result detail', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((component as any).result()).toBeTruthy();
    expect((component as any).result()!.result_id).toBe('550e8400-e29b-41d4-a716-446655440000');
  });

  it('should set first PCD label as active', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((component as any).activeLabel()).toBe('empty');
  });

  it('should switch active tab on setActiveTab call', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (component as any).setActiveTab({label: 'loaded', url: '/api/v1/results/.../pcd/loaded'});
    expect((component as any).activeLabel()).toBe('loaded');
  });

  it('should render metadata table', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const metaTable = fixture.nativeElement.querySelector('app-metadata-table');
    expect(metaTable).toBeTruthy();
  });

  it('should show not-found state on 404 error', async () => {
    apiSpy.getResultDetail.mockReturnValue(throwError(() => ({status: 404})));

    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect((component as any).notFound()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Result not found');
  });
});
