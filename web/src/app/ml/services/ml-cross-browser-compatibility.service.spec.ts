// Cross-Browser Compatibility Tests
import { TestBed } from '@angular/core/testing';
import { MLCrossBrowserCompatibilityService } from '../services/ml-cross-browser-compatibility.service';

describe('MLCrossBrowserCompatibilityService', () => {
  let service: MLCrossBrowserCompatibilityService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(MLCrossBrowserCompatibilityService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should detect browser capabilities', () => {
    const capabilities = service.capabilities();
    expect(capabilities.name).toBeDefined();
    expect(capabilities.version).toBeDefined();
    expect(typeof capabilities.webgl2).toBe('boolean');
    expect(typeof capabilities.webworkers).toBe('boolean');
  });

  it('should generate compatibility report', () => {
    const report = service.report();
    expect(report).toBeDefined();
    expect(typeof report.compatible).toBe('boolean');
    expect(Array.isArray(report.warnings)).toBe(true);
    expect(Array.isArray(report.errors)).toBe(true);
  });

  it('should check feature support', () => {
    const webgl2Support = service.isFeatureSupported('webgl2');
    expect(typeof webgl2Support).toBe('boolean');
  });

  it('should provide browser optimizations', () => {
    const optimizations = service.getBrowserOptimizations();
    expect(optimizations).toBeDefined();
    expect(optimizations.maxTextureSize).toBeGreaterThan(0);
  });

  it('should provide fallback configuration', () => {
    const fallback = service.getFallbackConfiguration();
    expect(fallback).toBeDefined();
    expect(typeof fallback.useWebGL1).toBe('boolean');
  });

  it('should test WebGL performance', async () => {
    const result = await service.testWebGLPerformance();
    expect(result).toBeDefined();
    expect(typeof result.score).toBe('number');
    expect(result.score >= 0).toBe(true);
  });

  // Test browser-specific behavior
  describe('Browser Detection', () => {
    it('should detect Chrome correctly', () => {
      // Mock Chrome user agent
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        configurable: true
      });
      
      const newService = new MLCrossBrowserCompatibilityService();
      expect(newService.capabilities().name).toBe('chrome');
    });

    it('should detect Firefox correctly', () => {
      // Mock Firefox user agent
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        configurable: true
      });
      
      const newService = new MLCrossBrowserCompatibilityService();
      expect(newService.capabilities().name).toBe('firefox');
    });
  });

  // Test WebGL detection
  describe('WebGL Detection', () => {
    it('should handle WebGL unavailable gracefully', () => {
      // Mock canvas getContext to return null
      const originalGetContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = jasmine.createSpy('getContext').and.returnValue(null);
      
      const newService = new MLCrossBrowserCompatibilityService();
      expect(newService.capabilities().webgl2).toBe(false);
      
      // Restore original method
      HTMLCanvasElement.prototype.getContext = originalGetContext;
    });
  });

  // Test performance monitoring
  describe('Performance Testing', () => {
    it('should complete performance test within reasonable time', async () => {
      const startTime = Date.now();
      await service.testWebGLPerformance();
      const endTime = Date.now();
      
      expect(endTime - startTime).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });
});