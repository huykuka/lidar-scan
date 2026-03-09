// Bounding Box Renderer Service
// Efficient 3D bounding box rendering for object detection results

import { Injectable } from '@angular/core';
import * as THREE from 'three';
import { BoundingBox3D } from '../../core/models/ml.model';

interface BoxRenderData {
  mesh: THREE.LineSegments;
  geometry: THREE.BufferGeometry;
  material: THREE.LineBasicMaterial;
  isActive: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class BoundingBoxRendererService {
  
  private readonly MAX_BOXES = 256;
  private boxPool: BoxRenderData[] = [];
  private scene?: THREE.Scene;
  private activeBoxCount = 0;
  
  /**
   * Initialize bounding box renderer with Three.js scene
   * @param scene Three.js scene to add boxes to
   */
  initialize(scene: THREE.Scene): void {
    this.scene = scene;
    this.createBoxPool();
  }
  
  /**
   * Update bounding boxes for current frame
   * @param boxes Array of bounding box data
   */
  updateBoundingBoxes(boxes: BoundingBox3D[]): void {
    if (!this.scene) {
      console.warn('BoundingBoxRenderer not initialized with scene');
      return;
    }
    
    // Hide all boxes first
    this.hideAllBoxes();
    
    // Update active boxes
    const numBoxes = Math.min(boxes.length, this.MAX_BOXES);
    this.activeBoxCount = numBoxes;
    
    for (let i = 0; i < numBoxes; i++) {
      this.updateBox(i, boxes[i]);
    }
  }
  
  /**
   * Update a single bounding box
   */
  private updateBox(index: number, box: BoundingBox3D): void {
    const boxData = this.boxPool[index];
    if (!boxData) return;
    
    // Update geometry for box wireframe
    this.updateBoxGeometry(boxData.geometry, box);
    
    // Update material color
    const color = new THREE.Color(
      box.color[0] / 255,
      box.color[1] / 255, 
      box.color[2] / 255
    );
    boxData.material.color = color;
    
    // Set visibility and active state
    boxData.mesh.visible = true;
    boxData.isActive = true;
    
    // Update position (center point)
    boxData.mesh.position.set(
      box.center[0],
      box.center[1], 
      box.center[2]
    );
    
    // Update rotation (yaw only for simplicity)
    boxData.mesh.rotation.set(0, 0, box.yaw);
  }
  
  /**
   * Generate 12-line cube wireframe geometry
   */
  private updateBoxGeometry(geometry: THREE.BufferGeometry, box: BoundingBox3D): void {
    const [dx, dy, dz] = box.size;
    const halfX = dx / 2;
    const halfY = dy / 2; 
    const halfZ = dz / 2;
    
    // 8 vertices of the box (relative to center)
    const vertices = [
      [-halfX, -halfY, -halfZ], // 0: bottom-front-left
      [+halfX, -halfY, -halfZ], // 1: bottom-front-right
      [+halfX, +halfY, -halfZ], // 2: bottom-back-right
      [-halfX, +halfY, -halfZ], // 3: bottom-back-left
      [-halfX, -halfY, +halfZ], // 4: top-front-left
      [+halfX, -halfY, +halfZ], // 5: top-front-right
      [+halfX, +halfY, +halfZ], // 6: top-back-right
      [-halfX, +halfY, +halfZ], // 7: top-back-left
    ];
    
    // 12 lines (24 points) forming the wireframe
    const lines = [
      // Bottom face
      [0, 1], [1, 2], [2, 3], [3, 0],
      // Top face  
      [4, 5], [5, 6], [6, 7], [7, 4],
      // Vertical edges
      [0, 4], [1, 5], [2, 6], [3, 7]
    ];
    
    const positions = new Float32Array(lines.length * 6); // 24 points * 3 coordinates
    
    for (let i = 0; i < lines.length; i++) {
      const [startIdx, endIdx] = lines[i];
      const start = vertices[startIdx];
      const end = vertices[endIdx];
      
      // Start point
      positions[i * 6] = start[0];
      positions[i * 6 + 1] = start[1];
      positions[i * 6 + 2] = start[2];
      
      // End point
      positions[i * 6 + 3] = end[0];
      positions[i * 6 + 4] = end[1];
      positions[i * 6 + 5] = end[2];
    }
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.attributes['position'].needsUpdate = true;
  }
  
  /**
   * Create pool of reusable box objects
   */
  private createBoxPool(): void {
    if (!this.scene) return;
    
    this.boxPool = [];
    
    for (let i = 0; i < this.MAX_BOXES; i++) {
      // Create geometry
      const geometry = new THREE.BufferGeometry();
      // Initialize with dummy box
      this.updateBoxGeometry(geometry, {
        id: i,
        label: 'temp',
        label_index: 0,
        confidence: 1.0,
        center: [0, 0, 0],
        size: [1, 1, 1],
        yaw: 0,
        color: [255, 255, 255]
      });
      
      // Create material
      const material = new THREE.LineBasicMaterial({
        color: 0xffffff,
        linewidth: 2,
        transparent: true,
        opacity: 0.8
      });
      
      // Create mesh
      const mesh = new THREE.LineSegments(geometry, material);
      mesh.visible = false;
      mesh.frustumCulled = false;
      
      // Coordinate system transformation (LiDAR to Three.js)
      mesh.rotation.x = -Math.PI / 2;
      mesh.rotation.z = -Math.PI / 2;
      
      this.scene.add(mesh);
      
      this.boxPool.push({
        mesh,
        geometry,
        material,
        isActive: false
      });
    }
    
    console.log(`BoundingBoxRenderer: Created pool of ${this.MAX_BOXES} boxes`);
  }
  
  /**
   * Hide all bounding boxes
   */
  private hideAllBoxes(): void {
    for (const boxData of this.boxPool) {
      boxData.mesh.visible = false;
      boxData.isActive = false;
    }
    this.activeBoxCount = 0;
  }
  
  /**
   * Get current number of active boxes
   */
  getActiveBoxCount(): number {
    return this.activeBoxCount;
  }
  
  /**
   * Set opacity for all boxes
   */
  setOpacity(opacity: number): void {
    for (const boxData of this.boxPool) {
      boxData.material.opacity = Math.max(0, Math.min(1, opacity));
    }
  }
  
  /**
   * Set line width for all boxes
   */
  setLineWidth(width: number): void {
    for (const boxData of this.boxPool) {
      boxData.material.linewidth = Math.max(1, width);
    }
  }
  
  /**
   * Toggle visibility of all bounding boxes
   */
  setVisible(visible: boolean): void {
    for (const boxData of this.boxPool) {
      if (boxData.isActive) {
        boxData.mesh.visible = visible;
      }
    }
  }
  
  /**
   * Cleanup resources
   */
  dispose(): void {
    for (const boxData of this.boxPool) {
      if (this.scene) {
        this.scene.remove(boxData.mesh);
      }
      boxData.geometry.dispose();
      boxData.material.dispose();
    }
    this.boxPool = [];
    this.activeBoxCount = 0;
  }
}