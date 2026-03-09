// ML API Service for Open3D-ML Integration
// Provides API access to ML models with mock data during development

import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, delay } from 'rxjs';

// Import from shared models
import {
  MLModelInfo,
  MLModelStatus,
  MLLoadRequest,
  BoundingBox3D,
  DetectionFrameMetadata,
  MLPerformanceMetrics
} from '../../core/models/ml.model';

@Injectable({
  providedIn: 'root'
})
export class MLApiService {
  
  private readonly API_BASE = '/api/v1/ml';
  
  // Reactive signals for ML state
  public readonly availableModels = signal<MLModelInfo[]>([]);
  public readonly modelStatuses = signal<Map<string, MLModelStatus>>(new Map());
  
  // Mock data flag - set to false when real backend is ready
  private readonly USE_MOCK_DATA = true;
  
  constructor(private http: HttpClient) {
    this.loadAvailableModels();
  }
  
  /**
   * Get list of available ML models
   */
  getModels(): Observable<MLModelInfo[]> {
    if (this.USE_MOCK_DATA) {
      return of(this.getMockModelData()).pipe(delay(200));
    }
    
    return this.http.get<MLModelInfo[]>(`${this.API_BASE}/models`);
  }
  
  /**
   * Get status of specific model
   */
  getModelStatus(modelKey: string): Observable<MLModelStatus> {
    if (this.USE_MOCK_DATA) {
      return of(this.getMockModelStatus(modelKey)).pipe(delay(150));
    }
    
    return this.http.get<MLModelStatus>(`${this.API_BASE}/models/${modelKey}/status`);
  }
  
  /**
   * Load model into memory
   */
  loadModel(modelKey: string, device: string = 'cpu'): Observable<any> {
    if (this.USE_MOCK_DATA) {
      return of({ model_key: modelKey, status: 'loading', message: 'Mock loading initiated' })
        .pipe(delay(300));
    }
    
    return this.http.post(`${this.API_BASE}/models/${modelKey}/load`, { device });
  }
  
  /**
   * Unload model from memory
   */
  unloadModel(modelKey: string): Observable<any> {
    if (this.USE_MOCK_DATA) {
      return of({ model_key: modelKey, status: 'unloaded' }).pipe(delay(100));
    }
    
    return this.http.delete(`${this.API_BASE}/models/${modelKey}`);
  }
  
  /**
   * Load available models and update signal
   */
  loadAvailableModels(): void {
    this.getModels().subscribe(models => {
      this.availableModels.set(models);
    });
  }
  
  /**
   * Mock data for development - matches api-spec.md exactly
   */
  private getMockModelData(): MLModelInfo[] {
    return [
      {
        model_key: "RandLANet__SemanticKITTI",
        model_name: "RandLANet", 
        dataset_name: "SemanticKITTI",
        task: "semantic_segmentation",
        num_classes: 19,
        class_names: [
          "unlabelled", "car", "bicycle", "motorcycle", "truck",
          "other-vehicle", "person", "bicyclist", "motorcyclist", 
          "road", "parking", "sidewalk", "other-ground", "building",
          "fence", "vegetation", "trunk", "terrain", "pole", "traffic-sign"
        ],
        color_map: [
          [0,0,0], [245,150,100], [245,230,100], [150,60,30], [180,30,80],
          [255,0,0], [30,30,255], [200,40,255], [90,30,150], [255,0,255],
          [255,150,255], [75,0,75], [75,0,175], [0,200,255], [50,120,255],
          [0,175,0], [0,60,135], [80,240,150], [150,240,255], [0,0,255]
        ],
        weight_url: "https://storage.googleapis.com/open3d-releases/model-zoo/randlanet_semantickitti_202201071330utc.pth",
        weight_filename: "randlanet_semantickitti_202201071330utc.pth",
        weight_size_mb: 8.2,
        config_file: "ml3d/configs/randlanet_semantickitti.yml",
        status: "available"
      },
      {
        model_key: "KPFCNN__SemanticKITTI",
        model_name: "KPFCNN",
        dataset_name: "SemanticKITTI", 
        task: "semantic_segmentation",
        num_classes: 19,
        class_names: ["unlabelled", "car", "..."],
        color_map: [[0,0,0], [245,150,100]],
        weight_url: "https://storage.googleapis.com/open3d-releases/model-zoo/kpconv_semantickitti_202009090354utc.pth",
        weight_filename: "kpconv_semantickitti_202009090354utc.pth",
        weight_size_mb: 18.4,
        config_file: "ml3d/configs/kpconv_semantickitti.yml",
        status: "available"
      },
      {
        model_key: "PointPillars__KITTI",
        model_name: "PointPillars",
        dataset_name: "KITTI",
        task: "object_detection",
        num_classes: 3,
        class_names: ["car", "pedestrian", "cyclist"],
        color_map: [[255,80,80], [80,255,80], [80,80,255]],
        weight_url: "https://storage.googleapis.com/open3d-releases/model-zoo/pointpillars_kitti_202012221652utc.pth",
        weight_filename: "pointpillars_kitti_202012221652utc.pth",
        weight_size_mb: 4.9,
        config_file: "ml3d/configs/pointpillars_kitti.yml",
        status: "available"
      },
      {
        model_key: "PointRCNN__KITTI",
        model_name: "PointRCNN",
        dataset_name: "KITTI",
        task: "object_detection", 
        num_classes: 3,
        class_names: ["car", "pedestrian", "cyclist"],
        color_map: [[255,80,80], [80,255,80], [80,80,255]],
        weight_url: "https://storage.googleapis.com/open3d-releases/model-zoo/pointrcnn_kitti_202105071146utc.pth",
        weight_filename: "pointrcnn_kitti_202105071146utc.pth",
        weight_size_mb: 14.1,
        config_file: "ml3d/configs/pointrcnn_kitti.yml",
        status: "available"
      }
    ];
  }
  
  /**
   * Generate synthetic LIDR v2 WebSocket frames for testing
   * @param pointCount Number of points to generate
   * @param hasLabels Include semantic labels
   * @param hasBoxes Include bounding boxes
   */
  generateMockLidrV2Frame(pointCount: number = 1000, hasLabels: boolean = true, hasBoxes: boolean = true): ArrayBuffer {
    // Calculate frame size
    const headerSize = 20; // magic(4) + version(4) + timestamp(8) + point_count(4)
    const flagsSize = 4;
    const positionsSize = pointCount * 12; // 3 floats per point
    const labelsSize = hasLabels ? pointCount * 4 : 0; // 1 int32 per point
    
    // Generate bounding boxes metadata
    const boxes: BoundingBox3D[] = hasBoxes ? this.generateMockBoundingBoxes() : [];
    const metadataJson = JSON.stringify({
      boxes,
      inference_time_ms: Math.random() * 100 + 50,
      model_key: "RandLANet__SemanticKITTI",
      timestamp: Date.now() / 1000
    });
    const metadataSize = hasBoxes ? 4 + metadataJson.length : 0; // length prefix + UTF-8 bytes
    
    const totalSize = headerSize + flagsSize + positionsSize + labelsSize + metadataSize;
    const buffer = new ArrayBuffer(totalSize);
    const view = new DataView(buffer);
    
    let offset = 0;
    
    // Header
    // Magic bytes "LIDR"
    view.setUint32(offset, 0x4C494452, false); offset += 4; // 'LIDR'
    // Version 2
    view.setUint32(offset, 2, true); offset += 4;
    // Timestamp
    view.setBigUint64(offset, BigInt(Math.floor(Date.now())), true); offset += 8;
    // Point count
    view.setUint32(offset, pointCount, true); offset += 4;
    
    // Flags
    let flags = 0;
    if (hasLabels) flags |= 1; // bit 0
    if (hasBoxes) flags |= 2;  // bit 1
    view.setUint32(offset, flags, true); offset += 4;
    
    // XYZ positions (Float32Array)
    const positions = new Float32Array(buffer, offset, pointCount * 3);
    for (let i = 0; i < pointCount; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 50;     // X: -25 to 25
      positions[i * 3 + 1] = (Math.random() - 0.5) * 50; // Y: -25 to 25  
      positions[i * 3 + 2] = Math.random() * 5;          // Z: 0 to 5
    }
    offset += positionsSize;
    
    // Semantic labels (Int32Array) - conditional
    if (hasLabels) {
      const labels = new Int32Array(buffer, offset, pointCount);
      for (let i = 0; i < pointCount; i++) {
        labels[i] = Math.floor(Math.random() * 19); // 0-18 semantic classes
      }
      offset += labelsSize;
    }
    
    // Bounding boxes metadata - conditional  
    if (hasBoxes) {
      // JSON length prefix
      view.setUint32(offset, metadataJson.length, true); offset += 4;
      // UTF-8 encoded JSON
      const encoder = new TextEncoder();
      const jsonBytes = encoder.encode(metadataJson);
      const jsonView = new Uint8Array(buffer, offset, jsonBytes.length);
      jsonView.set(jsonBytes);
    }
    
    return buffer;
  }
  
  /**
   * Generate realistic mock bounding boxes for testing
   */
  private generateMockBoundingBoxes(): BoundingBox3D[] {
    const boxes: BoundingBox3D[] = [];
    const numBoxes = Math.floor(Math.random() * 8) + 2; // 2-9 boxes
    const classNames = ['car', 'pedestrian', 'cyclist'];
    const colors = [[255,80,80], [80,255,80], [80,80,255]];
    
    for (let i = 0; i < numBoxes; i++) {
      const classIndex = Math.floor(Math.random() * classNames.length);
      boxes.push({
        id: i,
        label: classNames[classIndex],
        label_index: classIndex,
        confidence: 0.6 + Math.random() * 0.4, // 60-100% confidence
        center: [
          (Math.random() - 0.5) * 40, // X: -20 to 20
          (Math.random() - 0.5) * 40, // Y: -20 to 20  
          1 + Math.random() * 2       // Z: 1 to 3
        ],
        size: [
          2 + Math.random() * 3,      // width: 2-5m
          1 + Math.random() * 2,      // height: 1-3m
          4 + Math.random() * 2       // length: 4-6m
        ],
        yaw: Math.random() * Math.PI * 2, // 0-360 degrees
        color: colors[classIndex]
      });
    }
    
    return boxes;
  }
  
  /**
   * Get performance metrics for ML operations
   */
  getPerformanceMetrics(): Observable<MLPerformanceMetrics> {
    if (this.USE_MOCK_DATA) {
      const metrics: MLPerformanceMetrics = {
        inference_fps: 15 + Math.random() * 10, // 15-25 FPS
        avg_inference_ms: 40 + Math.random() * 60, // 40-100ms
        gpu_utilization_pct: 60 + Math.random() * 30, // 60-90%
        memory_usage_mb: 2000 + Math.random() * 1000, // 2-3GB
        points_processed_per_sec: 50000 + Math.random() * 20000 // 50k-70k points/sec
      };
      return of(metrics).pipe(delay(100));
    }
    
    return this.http.get<MLPerformanceMetrics>(`${this.API_BASE}/metrics`);
  }
  
  /**
   * Mock model status responses
   */
  private getMockModelStatus(modelKey: string): MLModelStatus {
    return {
      model_key: modelKey,
      status: "ready",
      device: "cpu", 
      loaded_at: Date.now() / 1000 - 100, // 100 seconds ago
      weight_cached: true,
      weight_path: `./models/${modelKey.toLowerCase().replace('__', '_')}.pth`,
      download_progress_pct: 100,
      last_inference_at: Date.now() / 1000 - 10, // 10 seconds ago
      inference_count: Math.floor(Math.random() * 200) + 50,
      avg_inference_ms: Math.random() * 100 + 50, // 50-150ms
      last_error: undefined
    };
  }
}