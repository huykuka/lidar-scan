// ML API Service for Open3D-ML Integration
// Provides API access to ML models with mock data during development

import { Injectable, computed, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, delay } from 'rxjs';

export interface MLModelInfo {
  model_key: string;
  model_name: string;
  dataset_name: string;
  task: 'semantic_segmentation' | 'object_detection';
  num_classes: number;
  class_names: string[];
  color_map: number[][];
  weight_url: string;
  weight_filename: string;
  weight_size_mb: number;
  config_file: string;
  status: 'available' | 'downloading' | 'loading' | 'ready' | 'error';
}

export interface MLModelStatus {
  model_key: string;
  status: 'not_loaded' | 'downloading' | 'loading' | 'ready' | 'error';
  device?: string;
  loaded_at?: number;
  weight_cached: boolean;
  weight_path?: string;
  download_progress_pct: number;
  last_inference_at?: number;
  inference_count: number;
  avg_inference_ms: number;
  last_error?: string;
}

export interface BoundingBox3D {
  id: number;
  label: string;
  label_index: number;
  confidence: number;
  center: number[]; // [x, y, z]
  size: number[];   // [dx, dy, dz]  
  yaw: number;
  color: number[];  // [R, G, B]
}

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
  private loadAvailableModels(): void {
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
      last_error: null
    };
  }
}