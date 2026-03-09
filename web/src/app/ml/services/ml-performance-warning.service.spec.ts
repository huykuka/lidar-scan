// Performance Warning Service Tests
import { TestBed } from '@angular/core/testing';
import { MLPerformanceWarningService } from '../services/ml-performance-warning.service';

describe('MLPerformanceWarningService', () => {
  let service: MLPerformanceWarningService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(MLPerformanceWarningService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should initialize with empty warnings', () => {
    const warnings = service.warnings();
    expect(Array.isArray(warnings)).toBe(true);
    expect(warnings.length).toBe(0);
  });

  it('should generate frame time warnings', () => {
    service.updateMetrics({ frameTime: 50 }); // Slow frame time
    
    const warnings = service.warnings();
    const frameWarning = warnings.find(w => w.category === 'performance' && w.id.includes('frame'));
    expect(frameWarning).toBeDefined();
    expect(frameWarning?.severity).toBeDefined();
  });

  it('should generate inference latency warnings', () => {
    service.updateMetrics({ inferenceLatency: 300 }); // High latency
    
    const warnings = service.warnings();
    const inferenceWarning = warnings.find(w => w.id.includes('inference'));
    expect(inferenceWarning).toBeDefined();
  });

  it('should generate memory warnings', () => {
    service.updateMetrics({ memoryUsage: 5000 }); // 5GB usage
    
    const warnings = service.warnings();
    const memoryWarning = warnings.find(w => w.category === 'memory');
    expect(memoryWarning).toBeDefined();
  });

  it('should calculate warning counts correctly', () => {
    service.updateMetrics({ 
      frameTime: 50,      // Error level
      inferenceLatency: 250, // Warning level
      memoryUsage: 3000   // Warning level
    });
    
    const counts = service.warningCounts();
    expect(counts.total).toBeGreaterThan(0);
    expect(counts.error + counts.warning + counts.info).toBe(counts.total);
  });

  it('should dismiss warnings', () => {
    service.updateMetrics({ frameTime: 50 });
    
    const initialWarnings = service.warnings();
    expect(initialWarnings.length).toBeGreaterThan(0);
    
    const warningId = initialWarnings[0].id;
    service.dismissWarning(warningId);
    
    const updatedWarnings = service.warnings();
    const dismissedWarning = updatedWarnings.find(w => w.id === warningId);
    expect(dismissedWarning).toBeUndefined();
  });

  it('should clear all warnings', () => {
    service.updateMetrics({ frameTime: 50, inferenceLatency: 300 });
    expect(service.warnings().length).toBeGreaterThan(0);
    
    service.clearAllWarnings();
    expect(service.warnings().length).toBe(0);
  });

  it('should enable degraded mode', () => {
    service.enableDegradedMode();
    
    const capabilities = service.getHardwareCapabilities();
    expect(capabilities.degradedMode).toBe(true);
    
    const warnings = service.warnings();
    const degradedModeWarning = warnings.find(w => w.id === 'degraded-mode-enabled');
    expect(degradedModeWarning).toBeDefined();
  });

  it('should disable degraded mode', () => {
    service.enableDegradedMode();
    service.disableDegradedMode();
    
    const capabilities = service.getHardwareCapabilities();
    expect(capabilities.degradedMode).toBe(false);
  });

  it('should detect when degraded mode should be enabled', () => {
    service.updateMetrics({ frameTime: 100 }); // Very slow
    
    const shouldEnable = service.shouldEnableDegradedMode();
    expect(typeof shouldEnable).toBe('boolean');
  });

  // Test warning cleanup
  it('should clean up old warnings automatically', (done) => {
    service.updateMetrics({ frameTime: 50 });
    expect(service.warnings().length).toBeGreaterThan(0);
    
    // Mock old timestamp
    const warnings = service.warnings();
    warnings[0].timestamp = Date.now() - 35000; // 35 seconds ago
    
    // Wait for cleanup cycle
    setTimeout(() => {
      // Trigger another update to force cleanup
      service.updateMetrics({ frameTime: 10 });
      
      const updatedWarnings = service.warnings();
      const oldWarning = updatedWarnings.find(w => w.timestamp < Date.now() - 30000);
      expect(oldWarning).toBeUndefined();
      done();
    }, 100);
  });

  // Test hardware detection
  describe('Hardware Detection', () => {
    it('should detect hardware capabilities', () => {
      const capabilities = service.getHardwareCapabilities();
      expect(capabilities).toBeDefined();
      expect(typeof capabilities.hasGPU).toBe('boolean');
      expect(typeof capabilities.isLowEnd).toBe('boolean');
    });
  });

  // Test performance thresholds
  describe('Performance Thresholds', () => {
    it('should use correct warning thresholds', () => {
      // Test frame time thresholds
      service.updateMetrics({ frameTime: 20 }); // Above 60 FPS threshold
      let warnings = service.warnings().filter(w => w.category === 'performance');
      expect(warnings.length).toBeGreaterThan(0);

      service.clearAllWarnings();
      
      service.updateMetrics({ frameTime: 40 }); // Above 30 FPS threshold  
      warnings = service.warnings().filter(w => w.severity === 'error');
      expect(warnings.length).toBeGreaterThan(0);
    });
  });
});