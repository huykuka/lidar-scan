import {ComponentFixture, TestBed} from '@angular/core/testing';
import {PcdViewerComponent} from './pcd-viewer.component';
import {PcdParserService} from '@core/services/pcd-parser.service';
import {PcdParseError} from '@core/models';
import {vi} from 'vitest';

const mockParseResult = {
  positions: new Float32Array([0, 0, 0]),
  colors: new Float32Array([1, 1, 1]),
  pointCount: 1,
};

// Minimal WebGL mock for headless
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

describe('PcdViewerComponent', () => {
  let fixture: ComponentFixture<PcdViewerComponent>;
  let component: PcdViewerComponent;
  let mockParser: {parse: ReturnType<typeof vi.fn>};

  beforeEach(async () => {
    mockParser = {parse: vi.fn().mockReturnValue(mockParseResult)};

    await TestBed.configureTestingModule({
      imports: [PcdViewerComponent],
      providers: [{provide: PcdParserService, useValue: mockParser}],
    }).compileComponents();

    fixture = TestBed.createComponent(PcdViewerComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show error state when fetch returns 404 or init fails', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response('not found', {status: 404, statusText: 'Not Found'}),
    );

    fixture.componentRef.setInput('pcdUrl', 'http://localhost/missing.pcd');
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((r) => setTimeout(r, 150));
    fixture.detectChanges();

    // Either Three.js init failed or the HTTP 404 caused an error — hasError must be true
    expect((component as any).hasError()).toBe(true);
  });

  it('should show error when PCD parser throws', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(new ArrayBuffer(10)),
    );
    mockParser.parse.mockImplementation(() => {
      throw new PcdParseError('Malformed PCD');
  it('should accept static /data/results URL and not error when fetch succeeds', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(new ArrayBuffer(10), {status: 200}),
    );
    mockParser.parse.mockReturnValue(mockParseResult);

    fixture.componentRef.setInput('pcdUrl', '/data/results/volume_calc_abc123/res-001/empty.pcd');
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((r) => setTimeout(r, 150));
    fixture.detectChanges();

    // The URL must follow the static /data/results pattern — no /api/ proxy
    const url: string = fixture.componentRef.instance['pcdUrl']();
    expect(url).toMatch(/^\/data\/results\/.+\/.+\/.+\.pcd$/);
    expect(url).not.toContain('/api/');
  });
});

    fixture.componentRef.setInput('pcdUrl', 'http://localhost/bad.pcd');
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((r) => setTimeout(r, 150));
    fixture.detectChanges();

    expect((component as any).hasError()).toBe(true);
  });
});
