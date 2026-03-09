// ML Node Status Component
// Shows ML model loading progress, inference metrics, and status

import { Component, computed, input, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MLApiService, MLModelStatus } from '../services/ml-api.service';

@Component({
  selector: 'app-ml-node-status',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="ml-node-status">
      <div class="status-header">
        <h4>ML Model Status</h4>
        <div class="status-indicator" [class]="statusClass()">
          {{ modelStatus()?.status || 'unknown' }}
        </div>
      </div>
      
      @if (modelStatus(); as status) {
        <div class="status-details">
          
          <!-- Model Info -->
          <div class="status-row">
            <span class="label">Model:</span>
            <span class="value">{{ modelKey() }}</span>
          </div>
          
          <div class="status-row">
            <span class="label">Device:</span>
            <span class="value">{{ status.device || 'N/A' }}</span>
          </div>
          
          <!-- Loading Progress -->
          @if (status.status === 'downloading') {
            <div class="status-row">
              <span class="label">Download:</span>
              <div class="progress-container">
                <div 
                  class="progress-bar"
                  [style.width.%]="status.download_progress_pct">
                </div>
                <span class="progress-text">{{ status.download_progress_pct }}%</span>
              </div>
            </div>
          }
          
          <!-- Inference Metrics -->
          @if (status.status === 'ready') {
            <div class="status-row">
              <span class="label">Avg Latency:</span>
              <span class="value">{{ status.avg_inference_ms | number:'1.1-1' }}ms</span>
            </div>
            
            <div class="status-row">
              <span class="label">Inference Count:</span>
              <span class="value">{{ status.inference_count }}</span>
            </div>
            
            @if (status.last_inference_at) {
              <div class="status-row">
                <span class="label">Last Inference:</span>
                <span class="value">{{ getTimeAgo(status.last_inference_at) }}</span>
              </div>
            }
          }
          
          <!-- Error Display -->
          @if (status.last_error) {
            <div class="status-row error">
              <span class="label">Error:</span>
              <span class="value">{{ status.last_error }}</span>
            </div>
          }
          
          <!-- Actions -->
          <div class="status-actions">
            @if (status.status === 'not_loaded') {
              <button 
                class="btn-primary"
                (click)="loadModel()">
                Load Model
              </button>
            } @else if (status.status === 'ready') {
              <button 
                class="btn-secondary"
                (click)="unloadModel()">
                Unload Model
              </button>
            }
          </div>
          
        </div>
      }
    </div>
  `,
  styles: [`
    .ml-node-status {
      background: var(--synergy-surface);
      border: 1px solid var(--synergy-border);
      border-radius: 6px;
      padding: 16px;
      margin: 8px 0;
    }
    
    .status-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    
    .status-header h4 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
    }
    
    .status-indicator {
      padding: 4px 8px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 500;
      text-transform: uppercase;
    }
    
    .status-indicator.not-loaded {
      background: var(--synergy-gray-100);
      color: var(--synergy-gray-700);
    }
    
    .status-indicator.downloading {
      background: var(--synergy-blue-100);
      color: var(--synergy-blue-700);
      animation: pulse 1.5s infinite;
    }
    
    .status-indicator.loading {
      background: var(--synergy-yellow-100);
      color: var(--synergy-yellow-700);
      animation: pulse 1.5s infinite;
    }
    
    .status-indicator.ready {
      background: var(--synergy-green-100);
      color: var(--synergy-green-700);
    }
    
    .status-indicator.error {
      background: var(--synergy-red-100);
      color: var(--synergy-red-700);
    }
    
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
    
    .status-details {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    
    .status-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
    }
    
    .status-row.error {
      color: var(--synergy-red-600);
    }
    
    .label {
      font-size: 12px;
      color: var(--synergy-gray-600);
      font-weight: 500;
    }
    
    .value {
      font-size: 12px;
      font-weight: 400;
    }
    
    .progress-container {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      max-width: 120px;
    }
    
    .progress-bar {
      height: 4px;
      background: var(--synergy-blue-500);
      border-radius: 2px;
      transition: width 0.3s ease;
      position: relative;
      overflow: hidden;
    }
    
    .progress-text {
      font-size: 11px;
      min-width: 35px;
      text-align: right;
    }
    
    .status-actions {
      margin-top: 12px;
      display: flex;
      gap: 8px;
    }
    
    .btn-primary, .btn-secondary {
      padding: 6px 12px;
      border-radius: 4px;
      border: none;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    
    .btn-primary {
      background: var(--synergy-primary);
      color: white;
    }
    
    .btn-primary:hover {
      background: var(--synergy-primary-dark);
    }
    
    .btn-secondary {
      background: var(--synergy-gray-200);
      color: var(--synergy-gray-700);
    }
    
    .btn-secondary:hover {
      background: var(--synergy-gray-300);
    }
  `]
})
export class MlNodeStatusComponent {
  
  // Input signals
  modelKey = input.required<string>();
  
  // Internal state
  modelStatus = computed(() => {
    const key = this.modelKey();
    return this.mlApi.modelStatuses().get(key);
  });
  
  statusClass = computed(() => {
    const status = this.modelStatus()?.status;
    return status?.replace('_', '-') || 'unknown';
  });
  
  constructor(private mlApi: MLApiService) {
    // Auto-refresh model status
    effect(() => {
      const key = this.modelKey();
      if (key) {
        this.refreshStatus();
      }
    });
  }
  
  refreshStatus(): void {
    const key = this.modelKey();
    this.mlApi.getModelStatus(key).subscribe(status => {
      const statusMap = new Map(this.mlApi.modelStatuses());
      statusMap.set(key, status);
      this.mlApi.modelStatuses.set(statusMap);
    });
  }
  
  loadModel(): void {
    const key = this.modelKey();
    this.mlApi.loadModel(key).subscribe(() => {
      // Start polling for status updates
      this.pollStatusUpdates();
    });
  }
  
  unloadModel(): void {
    const key = this.modelKey();
    this.mlApi.unloadModel(key).subscribe(() => {
      this.refreshStatus();
    });
  }
  
  getTimeAgo(timestamp: number): string {
    const seconds = Math.floor(Date.now() / 1000 - timestamp);
    
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }
  
  private pollStatusUpdates(): void {
    const poll = () => {
      const status = this.modelStatus();
      if (status?.status === 'downloading' || status?.status === 'loading') {
        setTimeout(() => {
          this.refreshStatus();
          poll();
        }, 1000);
      }
    };
    poll();
  }
}