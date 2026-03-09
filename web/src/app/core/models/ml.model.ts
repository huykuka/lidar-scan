// ML-specific TypeScript interfaces
// Matches api-spec.md for Open3D-ML integration

export interface MLModelInfo {
  model_key: string;
  model_name: string;
  dataset_name: string;
  task: 'semantic_segmentation' | 'object_detection';
  num_classes: number;
  class_names: string[];
  color_map: number[][]; // RGB color arrays
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

export interface MLLoadRequest {
  device: string; // 'cpu' | 'cuda:0' | 'cuda:1'
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

export interface DetectionFrameMetadata {
  boxes: BoundingBox3D[];
  inference_time_ms: number;
  model_key: string;
  timestamp: number;
}

// LIDR v2 WebSocket frame structure
export interface LidrV2Frame {
  magic: string; // 'LIDR'
  version: number; // 2
  timestamp: number;
  point_count: number;
  flags: number; // bit 0: has_labels, bit 1: has_boxes
  positions: Float32Array; // XYZ coordinates
  labels?: Int32Array; // Semantic labels (conditional)
  metadata?: DetectionFrameMetadata; // Bounding boxes metadata (conditional)
}

// ML Node Configuration interfaces
export interface MLSegmentationConfig {
  op_type: 'ml_semantic_segmentation';
  model_name: string;
  dataset_name: string;
  device: string;
  throttle_ms: number;
  num_points: number;
}

export interface MLDetectionConfig {
  op_type: 'ml_object_detection';
  model_name: string;
  dataset_name: string;
  device: string;
  throttle_ms: number;
  confidence_threshold: number;
}

// Semantic color constants
export const SEMANTIC_KITTI_COLOR_MAP: number[][] = [
  [0,0,0],        // unlabelled
  [245,150,100],  // car
  [245,230,100],  // bicycle
  [150,60,30],    // motorcycle
  [180,30,80],    // truck
  [255,0,0],      // other-vehicle
  [30,30,255],    // person
  [200,40,255],   // bicyclist
  [90,30,150],    // motorcyclist
  [255,0,255],    // road
  [255,150,255],  // parking
  [75,0,75],      // sidewalk
  [75,0,175],     // other-ground
  [0,200,255],    // building
  [50,120,255],   // fence
  [0,175,0],      // vegetation
  [0,60,135],     // trunk
  [80,240,150],   // terrain
  [150,240,255],  // pole
  [0,0,255]       // traffic-sign
];

export const SEMANTIC_KITTI_CLASS_NAMES: string[] = [
  "unlabelled", "car", "bicycle", "motorcycle", "truck",
  "other-vehicle", "person", "bicyclist", "motorcyclist", 
  "road", "parking", "sidewalk", "other-ground", "building",
  "fence", "vegetation", "trunk", "terrain", "pole", "traffic-sign"
];

// Performance metrics for ML operations
export interface MLPerformanceMetrics {
  inference_fps: number;
  avg_inference_ms: number;
  gpu_utilization_pct: number;
  memory_usage_mb: number;
  points_processed_per_sec: number;
}