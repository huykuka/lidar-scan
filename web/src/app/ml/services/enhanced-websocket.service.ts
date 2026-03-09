// Enhanced WebSocket Service with LIDR v2 support
// Extends existing WebSocket service for ML-enhanced point cloud streaming

import { Injectable, signal, computed } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { WebsocketService } from '../../core/services/websocket.service';
import { LidrV2DecoderService } from './lidr-v2-decoder.service';
import { LidrV2Frame } from '../../core/models/ml.model';

export interface EnhancedFrameData {
  version: number;
  timestamp: number;
  positions: Float32Array;
  point_count: number;
  // V2 specific fields
  labels?: Int32Array;
  boxes?: any[];
  inference_time_ms?: number;
  model_key?: string;
}

@Injectable({
  providedIn: 'root'
})
export class EnhancedWebsocketService {
  
  // Frame data signals
  private _currentFrame = signal<EnhancedFrameData | null>(null);
  private _frameCount = signal<number>(0);
  private _isStreaming = signal<boolean>(false);
  
  // Frame subjects for observers
  private frameSubject = new Subject<EnhancedFrameData>();
  private v2FrameSubject = new Subject<LidrV2Frame>();
  
  // Public observables
  public frames$ = this.frameSubject.asObservable();
  public v2Frames$ = this.v2FrameSubject.asObservable();
  
  // Public computed signals  
  currentFrame = computed(() => this._currentFrame());
  frameCount = computed(() => this._frameCount());
  isStreaming = computed(() => this._isStreaming());
  
  hasSemanticLabels = computed(() => {
    const frame = this._currentFrame();
    return !!(frame && frame.labels && frame.labels.length > 0);
  });
  
  hasBoundingBoxes = computed(() => {
    const frame = this._currentFrame();
    return !!(frame && frame.boxes && frame.boxes.length > 0);
  });
  
  constructor(
    private websocket: WebsocketService,
    private lidrDecoder: LidrV2DecoderService
  ) {
    this.setupMessageHandling();
  }
  
  /**
   * Connect to WebSocket and start streaming
   */
  connect(url: string): void {
    this._isStreaming.set(true);
    this.websocket.connect(url);
  }
  
  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    this._isStreaming.set(false);
    this._currentFrame.set(null);
    this._frameCount.set(0);
    this.websocket.disconnect();
  }
  
  /**
   * Setup message handling for both v1 and v2 frames
   */
  private setupMessageHandling(): void {
    this.websocket.messages$.subscribe((data: ArrayBuffer) => {
      this.processIncomingFrame(data);
    });
  }
  
  /**
   * Process incoming binary frame data
   */
  private processIncomingFrame(buffer: ArrayBuffer): void {
    try {
      // Detect LIDR version
      const version = this.lidrDecoder.detectLidrVersion(buffer);
      
      if (version === 2) {
        this.processV2Frame(buffer);
      } else if (version === 1) {
        this.processV1Frame(buffer);
      } else {
        // Assume raw point cloud data (legacy)
        this.processLegacyFrame(buffer);
      }
      
      this._frameCount.update(count => count + 1);
    } catch (error) {
      console.error('Error processing WebSocket frame:', error);
    }
  }
  
  /**
   * Process LIDR v2 frame with ML data
   */
  private processV2Frame(buffer: ArrayBuffer): void {
    const v2Frame = this.lidrDecoder.decodeLidrV2Frame(buffer);
    if (!v2Frame) {
      console.warn('Failed to decode LIDR v2 frame');
      return;
    }
    
    // Convert to enhanced frame data
    const enhancedFrame: EnhancedFrameData = {
      version: v2Frame.version,
      timestamp: v2Frame.timestamp,
      positions: v2Frame.positions,
      point_count: v2Frame.point_count,
      labels: v2Frame.labels,
      boxes: v2Frame.metadata?.boxes,
      inference_time_ms: v2Frame.metadata?.inference_time_ms,
      model_key: v2Frame.metadata?.model_key
    };
    
    this._currentFrame.set(enhancedFrame);
    this.frameSubject.next(enhancedFrame);
    this.v2FrameSubject.next(v2Frame);
  }
  
  /**
   * Process LIDR v1 frame (backward compatibility)
   */
  private processV1Frame(buffer: ArrayBuffer): void {
    const v1Frame = this.lidrDecoder.decodeLidrV1Frame(buffer);
    if (!v1Frame) {
      console.warn('Failed to decode LIDR v1 frame');
      return;
    }
    
    const enhancedFrame: EnhancedFrameData = {
      version: 1,
      timestamp: Date.now(),
      positions: v1Frame.positions,
      point_count: v1Frame.point_count
    };
    
    this._currentFrame.set(enhancedFrame);
    this.frameSubject.next(enhancedFrame);
  }
  
  /**
   * Process legacy raw point cloud data
   */
  private processLegacyFrame(buffer: ArrayBuffer): void {
    try {
      const pointCount = Math.floor(buffer.byteLength / 12); // Assume XYZ floats
      const positions = new Float32Array(buffer);
      
      const enhancedFrame: EnhancedFrameData = {
        version: 0, // Legacy
        timestamp: Date.now(),
        positions: positions,
        point_count: pointCount
      };
      
      this._currentFrame.set(enhancedFrame);
      this.frameSubject.next(enhancedFrame);
    } catch (error) {
      console.error('Error processing legacy frame:', error);
    }
  }
  
  /**
   * Get performance metrics for current streaming session
   */
  getStreamingMetrics() {
    return {
      frameCount: this._frameCount(),
      isStreaming: this._isStreaming(),
      hasML: this.hasSemanticLabels() || this.hasBoundingBoxes(),
      currentVersion: this._currentFrame()?.version || 0
    };
  }
  
  /**
   * Reset frame counter
   */
  resetFrameCount(): void {
    this._frameCount.set(0);
  }
}