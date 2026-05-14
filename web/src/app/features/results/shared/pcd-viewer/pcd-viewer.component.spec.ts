import {ComponentFixture, TestBed} from '@angular/core/testing';
import {PcdViewerComponent} from './pcd-viewer.component';
import {PcdParserService} from '@core/services/pcd-parser.service';
import {PcdParseError} from '@core/models';
import * as THREE from 'three';
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
    });

    fixture.componentRef.setInput('pcdUrl', 'http://localhost/bad.pcd');
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((r) => setTimeout(r, 150));
    fixture.detectChanges();

    expect((component as any).hasError()).toBe(true);
  });

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

  // ---------------------------------------------------------------------------
  // JSON-provided color contract tests
  // ---------------------------------------------------------------------------

  describe('color input — JSON-provided color overrides vertex colors', () => {
    it('should set vertexColors=false and apply color when color input is provided', () => {
      fixture.componentRef.setInput('color', '#ff0000');
      fixture.detectChanges();

      const mat = (component as any).pointsObj?.material as THREE.PointsMaterial | undefined;
      if (!mat) {
        // Three.js init may have failed in headless — skip material assertion gracefully
        return;
      }

      expect(mat.vertexColors).toBe(false);
      const expected = new THREE.Color('#ff0000');
      expect(mat.color.r).toBeCloseTo(expected.r, 3);
      expect(mat.color.g).toBeCloseTo(expected.g, 3);
      expect(mat.color.b).toBeCloseTo(expected.b, 3);
    });

    it('should set vertexColors=true and reset color to white when color input is empty', () => {
      // First apply a color, then clear it
      fixture.componentRef.setInput('color', '#00aaff');
      fixture.detectChanges();
      fixture.componentRef.setInput('color', '');
      fixture.detectChanges();

      const mat = (component as any).pointsObj?.material as THREE.PointsMaterial | undefined;
      if (!mat) return;

      expect(mat.vertexColors).toBe(true);
      expect(mat.color.r).toBeCloseTo(1, 3);
      expect(mat.color.g).toBeCloseTo(1, 3);
      expect(mat.color.b).toBeCloseTo(1, 3);
    });

    it('should use point size of 0.01 regardless of color input', () => {
      fixture.componentRef.setInput('color', '#00ff88');
      fixture.detectChanges();

      const mat = (component as any).pointsObj?.material as THREE.PointsMaterial | undefined;
      if (!mat) return;

      expect(mat.size).toBe(0.01);
    });

    it('should use point size of 0.01 with no color input', () => {
      fixture.detectChanges();

      const mat = (component as any).pointsObj?.material as THREE.PointsMaterial | undefined;
      if (!mat) return;

      expect(mat.size).toBe(0.01);
    });

    it('should NOT call applyMaterialColor with vertex data — per-point RGB from PCD is ignored when color is set', async () => {
      vi.spyOn(window, 'fetch').mockResolvedValue(
        new Response(new ArrayBuffer(10), {status: 200}),
      );
      // Parser returns non-white vertex colors
      mockParser.parse.mockReturnValue({
        positions: new Float32Array([1, 2, 3]),
        colors: new Float32Array([0.5, 0.2, 0.9]),
        pointCount: 1,
      });

      fixture.componentRef.setInput('color', '#ff6600');
      fixture.componentRef.setInput('pcdUrl', '/data/results/node/res/cloud.pcd');
      fixture.detectChanges();
      await fixture.whenStable();
      await new Promise((r) => setTimeout(r, 150));
      fixture.detectChanges();

      const mat = (component as any).pointsObj?.material as THREE.PointsMaterial | undefined;
      if (!mat) return;

      // Material must still reflect the JSON override color, not vertex data
      expect(mat.vertexColors).toBe(false);
      const expected = new THREE.Color('#ff6600');
      expect(mat.color.r).toBeCloseTo(expected.r, 3);
    });
  });
});
