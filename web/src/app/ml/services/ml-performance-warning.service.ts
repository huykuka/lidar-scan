// ML Performance Warning Service
// Monitors ML operations and provides performance warnings

import { Injectable, signal, computed } from '@angular/core';
import { interval, combineLatest } from 'rxjs';
import { map } from 'rxjs/operators';

interface PerformanceMetrics {
  frameTime: number;
  inferenceLatency: number;
  memoryUsage: number;
  gpuUtilization: number;
  activeModels: number;
}

interface PerformanceWarning {
  id: string;
  severity: 'info' | 'warning' | 'error';
  message: string;
  suggestion: string;
  timestamp: number;
  category: 'performance' | 'memory' | 'device' | 'model';
}

@Injectable({
  providedIn: 'root'
})
export class MLPerformanceWarningService {
  
  // Performance thresholds
  private readonly THRESHOLDS = {
    FRAME_TIME_WARNING: 16.67, // 60 FPS threshold (ms)
    FRAME_TIME_ERROR: 33.33,   // 30 FPS threshold (ms)
    INFERENCE_WARNING: 200,     // Inference latency warning (ms)
    INFERENCE_ERROR: 500,       // Inference latency error (ms)
    MEMORY_WARNING: 4096,       // Memory usage warning (MB)
    MEMORY_ERROR: 8192,         // Memory usage error (MB)
    GPU_UTILIZATION_WARNING: 90, // GPU utilization warning (%)
    MAX_CONCURRENT_MODELS: 2     // Maximum concurrent models
  };
  
  // Current metrics
  private readonly currentMetrics = signal<PerformanceMetrics>({
    frameTime: 0,
    inferenceLatency: 0,
    memoryUsage: 0,
    gpuUtilization: 0,
    activeModels: 0
  });
  
  // Active warnings
  public readonly warnings = signal<PerformanceWarning[]>([]);
  
  // Computed warning counts by severity
  public readonly warningCounts = computed(() => {
    const warns = this.warnings();
    return {
      total: warns.length,
      info: warns.filter(w => w.severity === 'info').length,
      warning: warns.filter(w => w.severity === 'warning').length,
      error: warns.filter(w => w.severity === 'error').length
    };
  });
  
  // Hardware capability detection
  private readonly hardwareCapabilities = signal({
    isLowEnd: false,
    hasGPU: false,
    totalMemory: 0,
    degradedMode: false
  });
  
  constructor() {
    this.detectHardwareCapabilities();
    this.startPerformanceMonitoring();
  }
  
  /**
   * Update performance metrics
   */
  updateMetrics(metrics: Partial<PerformanceMetrics>): void {
    const current = this.currentMetrics();
    this.currentMetrics.set({ ...current, ...metrics });
    this.checkPerformanceWarnings();
  }
  
  /**
   * Check for performance issues and generate warnings
   */
  private checkPerformanceWarnings(): void {
    const metrics = this.currentMetrics();
    const newWarnings: PerformanceWarning[] = [];
    
    // Frame time warnings
    if (metrics.frameTime > this.THRESHOLDS.FRAME_TIME_ERROR) {
      newWarnings.push({
        id: 'frame-time-critical',
        severity: 'error',
        message: `Rendering is very slow (${metrics.frameTime.toFixed(1)}ms/frame)`,
        suggestion: 'Enable degraded rendering mode or reduce bounding box count',
        timestamp: Date.now(),
        category: 'performance'
      });
    } else if (metrics.frameTime > this.THRESHOLDS.FRAME_TIME_WARNING) {
      newWarnings.push({
        id: 'frame-time-warning',
        severity: 'warning',
        message: `Frame rate below 60 FPS (${metrics.frameTime.toFixed(1)}ms/frame)`,
        suggestion: 'Consider reducing LOD distances or enabling performance mode',
        timestamp: Date.now(),
        category: 'performance'
      });
    }
    
    // Inference latency warnings
    if (metrics.inferenceLatency > this.THRESHOLDS.INFERENCE_ERROR) {
      newWarnings.push({
        id: 'inference-critical',
        severity: 'error',
        message: `ML inference is very slow (${metrics.inferenceLatency.toFixed(0)}ms)`,
        suggestion: 'Switch to GPU processing or reduce point cloud size',
        timestamp: Date.now(),
        category: 'performance'
      });
    } else if (metrics.inferenceLatency > this.THRESHOLDS.INFERENCE_WARNING) {
      newWarnings.push({
        id: 'inference-warning',
        severity: 'warning',
        message: `ML inference latency is high (${metrics.inferenceLatency.toFixed(0)}ms)`,
        suggestion: 'Consider increasing throttle interval or optimizing model settings',
        timestamp: Date.now(),
        category: 'performance'
      });
    }
    
    // Memory warnings
    if (metrics.memoryUsage > this.THRESHOLDS.MEMORY_ERROR) {
      newWarnings.push({
        id: 'memory-critical',
        severity: 'error',
        message: `High memory usage (${(metrics.memoryUsage / 1024).toFixed(1)}GB)`,
        suggestion: 'Unload unused models or restart the application',
        timestamp: Date.now(),
        category: 'memory'
      });
    } else if (metrics.memoryUsage > this.THRESHOLDS.MEMORY_WARNING) {
      newWarnings.push({
        id: 'memory-warning',
        severity: 'warning',
        message: `Elevated memory usage (${(metrics.memoryUsage / 1024).toFixed(1)}GB)`,
        suggestion: 'Monitor memory usage and consider unloading unused models',
        timestamp: Date.now(),
        category: 'memory'
      });
    }
    
    // GPU utilization warnings
    if (metrics.gpuUtilization > this.THRESHOLDS.GPU_UTILIZATION_WARNING) {
      newWarnings.push({
        id: 'gpu-utilization-high',
        severity: 'warning',
        message: `High GPU utilization (${metrics.gpuUtilization.toFixed(0)}%)`,
        suggestion: 'GPU is under heavy load - performance may be impacted',
        timestamp: Date.now(),
        category: 'device'
      });
    }
    
    // Multiple models warning
    if (metrics.activeModels > this.THRESHOLDS.MAX_CONCURRENT_MODELS) {
      newWarnings.push({
        id: 'too-many-models',
        severity: 'warning',
        message: `Too many models loaded simultaneously (${metrics.activeModels})`,
        suggestion: 'Unload unused models to free memory and improve performance',
        timestamp: Date.now(),
        category: 'model'
      });
    }
    
    // Hardware-specific warnings
    if (this.hardwareCapabilities().isLowEnd && !this.hardwareCapabilities().degradedMode) {
      newWarnings.push({
        id: 'hardware-limited',
        severity: 'info',
        message: 'Low-end hardware detected',
        suggestion: 'Enable degraded rendering mode for better performance',
        timestamp: Date.now(),
        category: 'device'
      });
    }
    
    // Update warnings (remove duplicates by ID)
    const existingWarnings = this.warnings().filter(w => 
      !newWarnings.some(nw => nw.id === w.id)
    );
    this.warnings.set([...existingWarnings, ...newWarnings]);
    
    // Auto-remove old warnings (older than 30 seconds)
    this.cleanupOldWarnings();
  }
  
  /**
   * Detect hardware capabilities
   */
  private detectHardwareCapabilities(): void {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    
    let hasGPU = false;
    let isLowEnd = false;
    let totalMemory = 0;
    
    if (gl) {
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) {
        const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
        hasGPU = !renderer.toLowerCase().includes('software');
        
        // Heuristic for low-end hardware detection
        isLowEnd = renderer.toLowerCase().includes('intel') && 
                   !renderer.toLowerCase().includes('iris');
      }
    }
    
    // Estimate memory from navigator if available
    if ('memory' in performance) {
      totalMemory = (performance as any).memory.jsHeapSizeLimit / (1024 * 1024);
    }
    
    this.hardwareCapabilities.set({
      hasGPU,
      isLowEnd,
      totalMemory,
      degradedMode: false
    });
  }
  
  /**
   * Start performance monitoring
   */
  private startPerformanceMonitoring(): void {
    // Monitor every 2 seconds
    interval(2000).subscribe(() => {
      this.checkPerformanceWarnings();
    });
  }
  
  /**
   * Remove old warnings
   */
  private cleanupOldWarnings(): void {
    const now = Date.now();
    const validWarnings = this.warnings().filter(warning => 
      now - warning.timestamp < 30000 // 30 seconds
    );
    
    if (validWarnings.length !== this.warnings().length) {
      this.warnings.set(validWarnings);
    }
  }
  
  /**
   * Dismiss a specific warning
   */
  dismissWarning(warningId: string): void {
    const filtered = this.warnings().filter(w => w.id !== warningId);
    this.warnings.set(filtered);
  }
  
  /**
   * Clear all warnings
   */
  clearAllWarnings(): void {
    this.warnings.set([]);
  }
  
  /**
   * Enable degraded performance mode
   */
  enableDegradedMode(): void {
    const caps = this.hardwareCapabilities();
    this.hardwareCapabilities.set({ ...caps, degradedMode: true });
    
    // Add info message about degraded mode
    this.warnings.update(warnings => [
      ...warnings.filter(w => w.id !== 'degraded-mode-enabled'),
      {
        id: 'degraded-mode-enabled',
        severity: 'info',
        message: 'Degraded rendering mode enabled',
        suggestion: 'Performance should be improved at the cost of visual quality',
        timestamp: Date.now(),
        category: 'performance'
      }
    ]);
  }
  
  /**
   * Disable degraded performance mode
   */
  disableDegradedMode(): void {
    const caps = this.hardwareCapabilities();
    this.hardwareCapabilities.set({ ...caps, degradedMode: false });
    this.dismissWarning('degraded-mode-enabled');
  }
  
  /**
   * Get hardware capabilities
   */
  getHardwareCapabilities() {
    return this.hardwareCapabilities();
  }
  
  /**
   * Check if degraded mode should be automatically enabled
   */
  shouldEnableDegradedMode(): boolean {
    const metrics = this.currentMetrics();
    const caps = this.hardwareCapabilities();
    
    return (caps.isLowEnd || 
            metrics.frameTime > this.THRESHOLDS.FRAME_TIME_ERROR ||
            metrics.memoryUsage > this.THRESHOLDS.MEMORY_WARNING) &&
           !caps.degradedMode;
  }
}