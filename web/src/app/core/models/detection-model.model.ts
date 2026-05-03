export interface DetectionModel {
  id: string;
  filename: string;
  display_name: string;
  model_type: string;
  file_size: number;
  uploaded_at: number;
  description: string;
  path: string;
}

export interface DetectionModelListResponse {
  models: DetectionModel[];
  count: number;
}

export interface DetectionModelUploadResponse {
  model: DetectionModel;
  message: string;
}

export interface DetectionModelDeleteResponse {
  deleted: boolean;
  message: string;
}
