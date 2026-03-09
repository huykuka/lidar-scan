// Cross-Browser Compatibility Service
// Handles browser-specific compatibility for ML features

import { Injectable, signal } from '@angular/core';

interface BrowserCapabilities {
  name: string;
  version: string;
  webgl2: boolean;
  webworkers: boolean;
  wasm: boolean;
  sharedArrayBuffer: boolean;
  bigInt: boolean;
  offscreenCanvas: boolean;
  transferableObjects: boolean;
  performanceObserver: boolean;
}

interface CompatibilityReport {
  compatible: boolean;
  warnings: string[];
  errors: string[];
  recommendations: string[];
  fallbacks: string[];
}

@Injectable({
  providedIn: 'root'
})
export class MLCrossBrowserCompatibilityService {
  
  // Browser capabilities
  public readonly capabilities = signal<BrowserCapabilities>({
    name: 'unknown',
    version: 'unknown',
    webgl2: false,
    webworkers: false,
    wasm: false,
    sharedArrayBuffer: false,
    bigInt: false,
    offscreenCanvas: false,
    transferableObjects: false,
    performanceObserver: false
  });
  
  // Compatibility report
  public readonly report = signal<CompatibilityReport>({
    compatible: false,
    warnings: [],
    errors: [],
    recommendations: [],
    fallbacks: []
  });
  
  // Feature availability
  private featureSupport = new Map<string, boolean>();
  
  constructor() {
    this.detectBrowserCapabilities();
    this.generateCompatibilityReport();
  }
  
  /**
   * Detect browser capabilities
   */
  private detectBrowserCapabilities(): void {
    const capabilities: BrowserCapabilities = {
      name: this.detectBrowserName(),
      version: this.detectBrowserVersion(),
      webgl2: this.checkWebGL2Support(),
      webworkers: this.checkWebWorkerSupport(),
      wasm: this.checkWASMSupport(),
      sharedArrayBuffer: this.checkSharedArrayBufferSupport(),
      bigInt: this.checkBigIntSupport(),
      offscreenCanvas: this.checkOffscreenCanvasSupport(),
      transferableObjects: this.checkTransferableObjectsSupport(),
      performanceObserver: this.checkPerformanceObserverSupport()
    };
    
    this.capabilities.set(capabilities);
    this.updateFeatureSupport(capabilities);
  }
  
  /**
   * Detect browser name
   */
  private detectBrowserName(): string {
    const userAgent = navigator.userAgent;
    
    if (userAgent.includes('Chrome') && !userAgent.includes('Edg')) return 'chrome';
    if (userAgent.includes('Firefox')) return 'firefox';
    if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) return 'safari';
    if (userAgent.includes('Edg')) return 'edge';
    if (userAgent.includes('Opera')) return 'opera';
    
    return 'unknown';
  }
  
  /**
   * Detect browser version
   */
  private detectBrowserVersion(): string {
    const userAgent = navigator.userAgent;
    const browserName = this.detectBrowserName();
    
    let versionRegex: RegExp;
    
    switch (browserName) {
      case 'chrome':
        versionRegex = /Chrome\/(\d+\.\d+)/;
        break;
      case 'firefox':
        versionRegex = /Firefox\/(\d+\.\d+)/;
        break;
      case 'safari':
        versionRegex = /Version\/(\d+\.\d+)/;
        break;
      case 'edge':
        versionRegex = /Edg\/(\d+\.\d+)/;
        break;
      default:
        return 'unknown';
    }
    
    const match = userAgent.match(versionRegex);
    return match ? match[1] : 'unknown';
  }
  
  /**
   * Check WebGL 2.0 support
   */
  private checkWebGL2Support(): boolean {
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl2');
      return gl !== null;
    } catch (error) {
      return false;
    }
  }
  
  /**
   * Check Web Worker support
   */
  private checkWebWorkerSupport(): boolean {
    return typeof Worker !== 'undefined';
  }
  
  /**
   * Check WebAssembly support
   */
  private checkWASMSupport(): boolean {
    return typeof WebAssembly === 'object' && typeof WebAssembly.instantiate === 'function';
  }
  
  /**
   * Check SharedArrayBuffer support
   */
  private checkSharedArrayBufferSupport(): boolean {
    return typeof SharedArrayBuffer !== 'undefined';
  }
  
  /**
   * Check BigInt support
   */
  private checkBigIntSupport(): boolean {
    return typeof BigInt !== 'undefined';
  }
  
  /**
   * Check OffscreenCanvas support
   */
  private checkOffscreenCanvasSupport(): boolean {
    return typeof OffscreenCanvas !== 'undefined';
  }
  
  /**
   * Check Transferable Objects support
   */
  private checkTransferableObjectsSupport(): boolean {
    try {
      // Test if we can create a transferable ArrayBuffer
      const buffer = new ArrayBuffer(1);
      const worker = new Worker(
        URL.createObjectURL(new Blob(['self.postMessage("test")'], { type: 'application/javascript' }))
      );
      worker.postMessage(buffer, [buffer]);
      worker.terminate();
      return buffer.byteLength === 0; // Should be transferred (emptied)
    } catch (error) {
      return false;
    }
  }
  
  /**
   * Check Performance Observer support
   */
  private checkPerformanceObserverSupport(): boolean {
    return typeof PerformanceObserver !== 'undefined';
  }
  
  /**
   * Update feature support map
   */
  private updateFeatureSupport(capabilities: BrowserCapabilities): void {
    this.featureSupport.clear();
    
    // Essential features for ML
    this.featureSupport.set('webgl2', capabilities.webgl2);
    this.featureSupport.set('webworkers', capabilities.webworkers);
    this.featureSupport.set('wasm', capabilities.wasm);
    this.featureSupport.set('bigint', capabilities.bigInt);
    
    // Performance features
    this.featureSupport.set('sharedArrayBuffer', capabilities.sharedArrayBuffer);
    this.featureSupport.set('offscreenCanvas', capabilities.offscreenCanvas);
    this.featureSupport.set('transferableObjects', capabilities.transferableObjects);
    this.featureSupport.set('performanceObserver', capabilities.performanceObserver);
    
    // Browser-specific checks
    this.featureSupport.set('chromium', ['chrome', 'edge', 'opera'].includes(capabilities.name));
    this.featureSupport.set('modernBrowser', this.isModernBrowser(capabilities));
  }
  
  /**
   * Check if browser is modern enough
   */
  private isModernBrowser(capabilities: BrowserCapabilities): boolean {
    const minVersions: Record<string, number> = {
      chrome: 80,
      firefox: 75,
      safari: 14,
      edge: 80
    };
    
    const currentVersion = parseFloat(capabilities.version);
    const minVersion = minVersions[capabilities.name] || 0;
    
    return currentVersion >= minVersion;
  }
  
  /**
   * Generate compatibility report
   */
  private generateCompatibilityReport(): void {
    const capabilities = this.capabilities();
    const warnings: string[] = [];
    const errors: string[] = [];
    const recommendations: string[] = [];
    const fallbacks: string[] = [];
    
    // Check essential features
    if (!capabilities.webgl2) {
      errors.push('WebGL 2.0 not supported - 3D rendering will be limited');
      fallbacks.push('Fall back to WebGL 1.0 with reduced features');
    }
    
    if (!capabilities.webworkers) {
      errors.push('Web Workers not supported - background processing unavailable');
      fallbacks.push('Process ML tasks on main thread with throttling');
    }
    
    if (!capabilities.wasm) {
      warnings.push('WebAssembly not supported - ML inference may be slower');
      fallbacks.push('Use JavaScript-based ML implementations');
    }
    
    if (!capabilities.bigInt) {
      warnings.push('BigInt not supported - large number calculations may be imprecise');
    }
    
    // Performance features
    if (!capabilities.sharedArrayBuffer) {
      warnings.push('SharedArrayBuffer not available - multi-threaded processing disabled');
      recommendations.push('Enable Cross-Origin-Embedder-Policy headers for SharedArrayBuffer support');
    }
    
    if (!capabilities.offscreenCanvas) {
      warnings.push('OffscreenCanvas not supported - background rendering unavailable');
      fallbacks.push('Render on main thread with frame limiting');
    }
    
    if (!capabilities.transferableObjects) {
      warnings.push('Transferable Objects not fully supported - data transfer may be slower');
    }
    
    if (!capabilities.performanceObserver) {
      warnings.push('Performance Observer not available - detailed metrics unavailable');
    }
    
    // Browser-specific issues
    if (capabilities.name === 'safari') {
      warnings.push('Safari has limited WebGL extensions - some features may not work');
      recommendations.push('Consider using Chrome or Firefox for full ML feature support');
    }
    
    if (capabilities.name === 'firefox' && parseFloat(capabilities.version) < 85) {
      warnings.push('Firefox version may have WebGL stability issues');
      recommendations.push('Update to Firefox 85+ for better WebGL support');
    }
    
    if (!this.featureSupport.get('modernBrowser')) {
      errors.push('Browser version is too old for full ML support');
      recommendations.push('Update to a more recent browser version');
    }
    
    // Generate overall compatibility status
    const compatible = errors.length === 0 && capabilities.webgl2 && capabilities.webworkers;
    
    this.report.set({
      compatible,
      warnings,
      errors,
      recommendations,
      fallbacks
    });
  }
  
  /**
   * Check if specific feature is supported
   */
  isFeatureSupported(feature: string): boolean {
    return this.featureSupport.get(feature) || false;
  }
  
  /**
   * Get browser-specific optimizations
   */
  getBrowserOptimizations(): Record<string, any> {
    const capabilities = this.capabilities();
    const optimizations: Record<string, any> = {};
    
    switch (capabilities.name) {
      case 'chrome':
        optimizations['webglExtensions'] = ['EXT_color_buffer_float', 'OES_texture_float_linear'];
        optimizations['maxTextureSize'] = 4096;
        optimizations['webworkerConcurrency'] = navigator.hardwareConcurrency || 4;
        break;
        
      case 'firefox':
        optimizations['webglExtensions'] = ['OES_texture_float'];
        optimizations['maxTextureSize'] = 2048; // More conservative
        optimizations['webworkerConcurrency'] = Math.max(2, (navigator.hardwareConcurrency || 4) - 1);
        break;
        
      case 'safari':
        optimizations['webglExtensions'] = ['OES_texture_float'];
        optimizations['maxTextureSize'] = 2048;
        optimizations['webworkerConcurrency'] = 2; // Safari has WebWorker limitations
        optimizations['usePolyfills'] = true;
        break;
        
      default:
        optimizations['maxTextureSize'] = 2048;
        optimizations['webworkerConcurrency'] = 2;
        optimizations['usePolyfills'] = true;
    }
    
    return optimizations;
  }
  
  /**
   * Get fallback configuration for unsupported browsers
   */
  getFallbackConfiguration(): Record<string, any> {
    const capabilities = this.capabilities();
    const config: Record<string, any> = {
      useWebGL1: !capabilities.webgl2,
      disableWebWorkers: !capabilities.webworkers,
      usePolyfills: !this.featureSupport.get('modernBrowser'),
      reducedPrecision: !capabilities.bigInt,
      limitConcurrency: !capabilities.sharedArrayBuffer,
      syncRendering: !capabilities.offscreenCanvas
    };
    
    return config;
  }
  
  /**
   * Test WebGL performance
   */
  testWebGLPerformance(): Promise<{ score: number; details: any }> {
    return new Promise((resolve) => {
      const canvas = document.createElement('canvas');
      canvas.width = 512;
      canvas.height = 512;
      
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      
      if (!gl) {
        resolve({ score: 0, details: { error: 'WebGL not available' } });
        return;
      }
      
      // Simple performance test
      const startTime = performance.now();
      
      // Create and render a simple geometry
      const vertices = new Float32Array([-1, -1, 1, -1, 0, 1]);
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
      
      // Render multiple frames
      let frames = 0;
      const maxFrames = 100;
      
      const renderFrame = () => {
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        frames++;
        
        if (frames < maxFrames) {
          requestAnimationFrame(renderFrame);
        } else {
          const endTime = performance.now();
          const totalTime = endTime - startTime;
          const fps = (maxFrames / totalTime) * 1000;
          
          resolve({
            score: Math.min(100, fps / 60 * 100), // Normalize to 60 FPS = 100 score
            details: {
              fps,
              totalTime,
              frames: maxFrames,
              renderer: gl.getParameter(gl.RENDERER),
              vendor: gl.getParameter(gl.VENDOR)
            }
          });
        }
      };
      
      renderFrame();
    });
  }
  
  /**
   * Run comprehensive compatibility test
   */
  async runCompatibilityTest(): Promise<CompatibilityReport & { performanceScore?: number }> {
    const report = this.report();
    
    try {
      const performanceTest = await this.testWebGLPerformance();
      
      return {
        ...report,
        performanceScore: performanceTest.score
      };
    } catch (error) {
      return {
        ...report,
        performanceScore: 0
      };
    }
  }
}