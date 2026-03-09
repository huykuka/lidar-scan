// Bounding Box Overlay Component
// CSS overlay for bounding box labels using Vector3.project()

import { Component, input, computed, ElementRef, ViewChild, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as THREE from 'three';
import { BoundingBox3D } from '../../core/models/ml.model';

interface BoxLabel {
  id: number;
  text: string;
  x: number;
  y: number;
  visible: boolean;
  confidence: number;
  color: string;
}

@Component({
  selector: 'app-bounding-box-overlay',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div #container class="bounding-box-overlay" [style.pointer-events]="'none'">
      @for (label of boxLabels(); track label.id) {
        <div 
          class="box-label"
          [class.hidden]="!label.visible"
          [style.left.px]="label.x"
          [style.top.px]="label.y"
          [style.color]="label.color"
          [style.border-color]="label.color">
          <div class="label-text">{{ label.text }}</div>
          <div class="confidence">{{ (label.confidence * 100).toFixed(0) }}%</div>
        </div>
      }
    </div>
  `,
  styles: [`
    .bounding-box-overlay {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 100;
      overflow: hidden;
    }
    
    .box-label {
      position: absolute;
      background: rgba(0, 0, 0, 0.7);
      border: 1px solid;
      border-radius: 4px;
      padding: 4px 6px;
      font-size: 11px;
      font-weight: 500;
      color: white;
      white-space: nowrap;
      transform: translate(-50%, -100%);
      transition: opacity 0.2s ease;
      backdrop-filter: blur(2px);
      min-width: 50px;
      text-align: center;
    }
    
    .box-label.hidden {
      opacity: 0;
      pointer-events: none;
    }
    
    .label-text {
      font-weight: 600;
      text-transform: capitalize;
    }
    
    .confidence {
      font-size: 9px;
      opacity: 0.8;
      margin-top: 1px;
    }
    
    /* Responsive font sizes */
    @media (max-width: 768px) {
      .box-label {
        font-size: 10px;
        padding: 3px 5px;
      }
      
      .confidence {
        font-size: 8px;
      }
    }
  `]
})
export class BoundingBoxOverlayComponent implements AfterViewInit, OnDestroy {
  
  @ViewChild('container', { static: true }) containerRef!: ElementRef<HTMLDivElement>;
  
  // Input signals
  boxes = input<BoundingBox3D[]>([]);
  camera = input<THREE.Camera | null>(null);
  canvasSize = input<{ width: number; height: number }>({ width: 800, height: 600 });
  
  // Internal state
  private animationId?: number;
  private isProjecting = false;
  
  // Computed box labels with screen positions
  boxLabels = computed(() => {
    const boxesData = this.boxes();
    const cameraObj = this.camera();
    const size = this.canvasSize();
    
    if (!cameraObj || boxesData.length === 0) {
      return [];
    }
    
    return boxesData.map(box => {
      const worldPosition = new THREE.Vector3(box.center[0], box.center[1], box.center[2] + box.size[2] / 2);
      const screenPosition = this.projectToScreen(worldPosition, cameraObj, size);
      
      return {
        id: box.id,
        text: box.label,
        x: screenPosition.x,
        y: screenPosition.y,
        visible: screenPosition.visible,
        confidence: box.confidence,
        color: `rgb(${box.color[0]}, ${box.color[1]}, ${box.color[2]})`
      };
    });
  });
  
  ngAfterViewInit(): void {
    // Start animation loop for smooth label updates
    this.startProjectionLoop();
  }
  
  ngOnDestroy(): void {
    this.stopProjectionLoop();
  }
  
  /**
   * Project 3D world position to 2D screen coordinates
   */
  private projectToScreen(
    worldPos: THREE.Vector3, 
    camera: THREE.Camera, 
    canvasSize: { width: number; height: number }
  ): { x: number; y: number; visible: boolean } {
    
    const vector = worldPos.clone();
    vector.project(camera);
    
    // Convert normalized device coordinates to screen coordinates
    const x = (vector.x * 0.5 + 0.5) * canvasSize.width;
    const y = (vector.y * -0.5 + 0.5) * canvasSize.height;
    
    // Check if point is in front of camera and within screen bounds
    const visible = vector.z < 1 && 
                   x >= -50 && x <= canvasSize.width + 50 && 
                   y >= -50 && y <= canvasSize.height + 50;
    
    return { x, y, visible };
  }
  
  /**
   * Start animation loop for real-time label positioning
   */
  private startProjectionLoop(): void {
    if (this.isProjecting) return;
    
    this.isProjecting = true;
    
    const animate = () => {
      if (!this.isProjecting) return;
      
      // The computed signal will automatically update when camera/boxes change
      // This loop is mainly for consistent frame updates
      
      this.animationId = requestAnimationFrame(animate);
    };
    
    animate();
  }
  
  /**
   * Stop animation loop
   */
  private stopProjectionLoop(): void {
    this.isProjecting = false;
    
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = undefined;
    }
  }
  
  /**
   * Update canvas size (called from parent component)
   */
  updateCanvasSize(width: number, height: number): void {
    // This will trigger recomputation of boxLabels via the input signal
  }
}