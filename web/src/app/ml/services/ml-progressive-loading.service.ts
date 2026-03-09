// ML Progressive Loading Service
// Handles progressive loading of large ML datasets and models

import { Injectable, signal } from '@angular/core';
import { BehaviorSubject, Observable, of } from 'rxjs';
import { delay, map, switchMap } from 'rxjs/operators';

interface LoadingChunk {
  id: string;
  type: 'model' | 'dataset' | 'weights';
  data: any;
  size: number;
  progress: number;
  complete: boolean;
}

interface ProgressiveLoadState {
  isLoading: boolean;
  totalChunks: number;
  loadedChunks: number;
  totalSize: number;
  loadedSize: number;
  currentChunk?: LoadingChunk;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class MLProgressiveLoadingService {
  
  // Loading state
  public readonly loadingState = signal<ProgressiveLoadState>({
    isLoading: false,
    totalChunks: 0,
    loadedChunks: 0,
    totalSize: 0,
    loadedSize: 0
  });
  
  // Queue of chunks to load
  private loadingQueue: LoadingChunk[] = [];
  private currentlyLoading = false;
  
  // Configuration
  private readonly CHUNK_SIZE = 1024 * 1024; // 1MB chunks
  private readonly MAX_CONCURRENT_LOADS = 2;
  private readonly LOAD_DELAY = 100; // ms between chunks
  
  constructor() {}
  
  /**
   * Load ML model progressively
   */
  loadModelProgressively(modelKey: string, modelSize: number): Observable<number> {
    return new Observable(observer => {
      const chunks = this.createModelChunks(modelKey, modelSize);
      this.queueChunks(chunks);
      
      const subscription = this.processLoadingQueue().subscribe({
        next: (progress) => observer.next(progress),
        complete: () => observer.complete(),
        error: (error) => observer.error(error)
      });
      
      return () => subscription.unsubscribe();
    });
  }
  
  /**
   * Load large point cloud dataset progressively
   */
  loadDatasetProgressively(datasetPath: string, estimatedSize: number): Observable<any[]> {
    return new Observable(observer => {
      const chunks = this.createDatasetChunks(datasetPath, estimatedSize);
      this.queueChunks(chunks);
      
      let accumulatedData: any[] = [];
      
      const subscription = this.processLoadingQueue().subscribe({
        next: (progress) => {
          // Emit partial data as it loads
          const currentChunk = this.loadingState().currentChunk;
          if (currentChunk?.data) {
            accumulatedData = [...accumulatedData, ...currentChunk.data];
            observer.next(accumulatedData);
          }
        },
        complete: () => observer.complete(),
        error: (error) => observer.error(error)
      });
      
      return () => subscription.unsubscribe();
    });
  }
  
  /**
   * Create model loading chunks
   */
  private createModelChunks(modelKey: string, totalSize: number): LoadingChunk[] {
    const numChunks = Math.ceil(totalSize / this.CHUNK_SIZE);
    const chunks: LoadingChunk[] = [];
    
    for (let i = 0; i < numChunks; i++) {
      const chunkSize = Math.min(this.CHUNK_SIZE, totalSize - (i * this.CHUNK_SIZE));
      chunks.push({
        id: `${modelKey}_chunk_${i}`,
        type: 'model',
        data: this.generateMockModelData(chunkSize),
        size: chunkSize,
        progress: 0,
        complete: false
      });
    }
    
    return chunks;
  }
  
  /**
   * Create dataset loading chunks
   */
  private createDatasetChunks(datasetPath: string, totalSize: number): LoadingChunk[] {
    const numChunks = Math.ceil(totalSize / this.CHUNK_SIZE);
    const chunks: LoadingChunk[] = [];
    
    for (let i = 0; i < numChunks; i++) {
      const chunkSize = Math.min(this.CHUNK_SIZE, totalSize - (i * this.CHUNK_SIZE));
      const pointsInChunk = Math.floor(chunkSize / (3 * 4)); // 3 floats per point
      
      chunks.push({
        id: `${datasetPath}_chunk_${i}`,
        type: 'dataset',
        data: this.generateMockPointCloudData(pointsInChunk),
        size: chunkSize,
        progress: 0,
        complete: false
      });
    }
    
    return chunks;
  }
  
  /**
   * Queue chunks for loading
   */
  private queueChunks(chunks: LoadingChunk[]): void {
    this.loadingQueue = [...this.loadingQueue, ...chunks];
    
    const totalSize = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
    const currentState = this.loadingState();
    
    this.loadingState.set({
      ...currentState,
      isLoading: true,
      totalChunks: currentState.totalChunks + chunks.length,
      totalSize: currentState.totalSize + totalSize
    });
  }
  
  /**
   * Process loading queue with progressive updates
   */
  private processLoadingQueue(): Observable<number> {
    if (this.currentlyLoading) {
      return of(0);
    }
    
    this.currentlyLoading = true;
    
    return new Observable(observer => {
      const processNext = () => {
        if (this.loadingQueue.length === 0) {
          this.finishLoading();
          observer.complete();
          return;
        }
        
        const chunk = this.loadingQueue.shift()!;
        this.loadChunk(chunk).subscribe({
          next: (progress) => {
            this.updateProgress(chunk, progress);
            const totalProgress = this.calculateTotalProgress();
            observer.next(totalProgress);
          },
          complete: () => {
            this.markChunkComplete(chunk);
            const totalProgress = this.calculateTotalProgress();
            observer.next(totalProgress);
            
            // Process next chunk after delay
            setTimeout(processNext, this.LOAD_DELAY);
          },
          error: (error) => {
            this.handleLoadingError(error);
            observer.error(error);
          }
        });
      };
      
      processNext();
    });
  }
  
  /**
   * Load individual chunk with simulated progress
   */
  private loadChunk(chunk: LoadingChunk): Observable<number> {
    return new Observable(observer => {
      let progress = 0;
      const increment = 10; // 10% increments
      
      const timer = setInterval(() => {
        progress += increment;
        chunk.progress = progress;
        observer.next(progress);
        
        if (progress >= 100) {
          clearInterval(timer);
          chunk.complete = true;
          observer.complete();
        }
      }, 50); // 50ms intervals for smooth progress
      
      return () => clearInterval(timer);
    });
  }
  
  /**
   * Update progress for a chunk
   */
  private updateProgress(chunk: LoadingChunk, progress: number): void {
    const currentState = this.loadingState();
    this.loadingState.set({
      ...currentState,
      currentChunk: { ...chunk, progress }
    });
  }
  
  /**
   * Mark chunk as complete
   */
  private markChunkComplete(chunk: LoadingChunk): void {
    const currentState = this.loadingState();
    this.loadingState.set({
      ...currentState,
      loadedChunks: currentState.loadedChunks + 1,
      loadedSize: currentState.loadedSize + chunk.size,
      currentChunk: undefined
    });
  }
  
  /**
   * Calculate total loading progress
   */
  private calculateTotalProgress(): number {
    const state = this.loadingState();
    if (state.totalSize === 0) return 0;
    
    let totalProgress = (state.loadedSize / state.totalSize) * 100;
    
    // Add progress from current chunk
    if (state.currentChunk) {
      const chunkContribution = (state.currentChunk.size / state.totalSize) * 100;
      const chunkProgress = (state.currentChunk.progress / 100) * chunkContribution;
      totalProgress += chunkProgress;
    }
    
    return Math.min(100, totalProgress);
  }
  
  /**
   * Finish loading process
   */
  private finishLoading(): void {
    this.currentlyLoading = false;
    this.loadingState.set({
      isLoading: false,
      totalChunks: 0,
      loadedChunks: 0,
      totalSize: 0,
      loadedSize: 0
    });
  }
  
  /**
   * Handle loading errors
   */
  private handleLoadingError(error: any): void {
    const currentState = this.loadingState();
    this.loadingState.set({
      ...currentState,
      isLoading: false,
      error: error.message || 'Loading failed'
    });
    this.currentlyLoading = false;
  }
  
  /**
   * Cancel current loading operation
   */
  cancelLoading(): void {
    this.loadingQueue = [];
    this.finishLoading();
  }
  
  /**
   * Generate mock model data for testing
   */
  private generateMockModelData(size: number): ArrayBuffer {
    const buffer = new ArrayBuffer(size);
    const view = new Uint8Array(buffer);
    
    // Fill with random data to simulate model weights
    for (let i = 0; i < size; i++) {
      view[i] = Math.floor(Math.random() * 256);
    }
    
    return buffer;
  }
  
  /**
   * Generate mock point cloud data for testing
   */
  private generateMockPointCloudData(pointCount: number): number[][] {
    const points: number[][] = [];
    
    for (let i = 0; i < pointCount; i++) {
      points.push([
        (Math.random() - 0.5) * 100, // X
        (Math.random() - 0.5) * 100, // Y
        Math.random() * 10           // Z
      ]);
    }
    
    return points;
  }
  
  /**
   * Get current loading progress percentage
   */
  getLoadingProgress(): number {
    return this.calculateTotalProgress();
  }
  
  /**
   * Check if currently loading
   */
  isCurrentlyLoading(): boolean {
    return this.loadingState().isLoading;
  }
  
  /**
   * Get loading state for UI components
   */
  getLoadingState() {
    return this.loadingState();
  }
}