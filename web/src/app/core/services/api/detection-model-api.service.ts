import {inject, Injectable} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Observable} from 'rxjs';
import {environment} from '../../../../environments/environment';
import {
  DetectionModel,
  DetectionModelDeleteResponse,
  DetectionModelListResponse,
  DetectionModelUploadResponse,
} from '../../models/detection-model.model';

@Injectable({
  providedIn: 'root',
})
export class DetectionModelApiService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/detection/models`;

  listModels(): Observable<DetectionModelListResponse> {
    return this.http.get<DetectionModelListResponse>(this.baseUrl);
  }

  getModel(modelId: string): Observable<DetectionModel> {
    return this.http.get<DetectionModel>(`${this.baseUrl}/${modelId}`);
  }

  uploadModel(file: File, displayName?: string, modelType?: string, description?: string): Observable<DetectionModelUploadResponse> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    if (displayName) {
      formData.append('display_name', displayName);
    }
    if (modelType) {
      formData.append('model_type', modelType);
    }
    if (description) {
      formData.append('description', description);
    }
    return this.http.post<DetectionModelUploadResponse>(`${this.baseUrl}/upload`, formData);
  }

  deleteModel(modelId: string): Observable<DetectionModelDeleteResponse> {
    return this.http.delete<DetectionModelDeleteResponse>(`${this.baseUrl}/${modelId}`);
  }
}
