// ML Context Menu Service
// Provides context menu actions for ML-specific operations

import { Injectable, signal } from '@angular/core';
import { BoundingBox3D } from '../../core/models/ml.model';

interface ContextMenuItem {
  id: string;
  label: string;
  icon?: string;
  disabled?: boolean;
  action: () => void;
}

interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  target?: {
    type: 'bounding-box' | 'ml-node' | 'point-cloud';
    data?: any;
  };
}

@Injectable({
  providedIn: 'root'
})
export class MLContextMenuService {
  
  // Context menu state
  public readonly contextMenu = signal<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0
  });
  
  // Current menu items
  public readonly menuItems = signal<ContextMenuItem[]>([]);
  
  constructor() {
    // Close context menu on outside click
    document.addEventListener('click', (event) => {
      if (this.contextMenu().visible) {
        this.hideContextMenu();
      }
    });
    
    // Close on escape key
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.contextMenu().visible) {
        this.hideContextMenu();
      }
    });
  }
  
  /**
   * Show context menu for bounding box
   */
  showBoundingBoxContextMenu(event: MouseEvent, box: BoundingBox3D): void {
    event.preventDefault();
    event.stopPropagation();
    
    const items: ContextMenuItem[] = [
      {
        id: 'inspect-box',
        label: `Inspect ${box.label}`,
        icon: 'info',
        action: () => this.inspectBoundingBox(box)
      },
      {
        id: 'copy-coordinates',
        label: 'Copy Coordinates',
        icon: 'content_copy',
        action: () => this.copyCoordinates(box)
      },
      {
        id: 'hide-class',
        label: `Hide all ${box.label}`,
        icon: 'visibility_off',
        action: () => this.hideClassType(box.label)
      },
      {
        id: 'export-box',
        label: 'Export Bounding Box',
        icon: 'download',
        action: () => this.exportBoundingBox(box)
      },
      {
        id: 'separator-1',
        label: '---',
        action: () => {}
      },
      {
        id: 'adjust-threshold',
        label: 'Adjust Confidence Threshold',
        icon: 'tune',
        action: () => this.adjustConfidenceThreshold(box.confidence)
      }
    ];
    
    this.showContextMenu(event.clientX, event.clientY, items, {
      type: 'bounding-box',
      data: box
    });
  }
  
  /**
   * Show context menu for ML node in flow canvas
   */
  showMLNodeContextMenu(event: MouseEvent, nodeId: string, nodeType: string): void {
    event.preventDefault();
    event.stopPropagation();
    
    const items: ContextMenuItem[] = [
      {
        id: 'warm-up-model',
        label: 'Warm Up Model',
        icon: 'play_arrow',
        action: () => this.warmUpModel(nodeId)
      },
      {
        id: 'reload-model',
        label: 'Reload Model',
        icon: 'refresh',
        action: () => this.reloadModel(nodeId)
      },
      {
        id: 'view-performance',
        label: 'View Performance Metrics',
        icon: 'analytics',
        action: () => this.viewPerformanceMetrics(nodeId)
      },
      {
        id: 'export-config',
        label: 'Export Configuration',
        icon: 'settings',
        action: () => this.exportNodeConfig(nodeId)
      },
      {
        id: 'separator-1',
        label: '---',
        action: () => {}
      },
      {
        id: 'duplicate-node',
        label: 'Duplicate Node',
        icon: 'content_copy',
        action: () => this.duplicateNode(nodeId)
      },
      {
        id: 'toggle-device',
        label: 'Switch CPU/GPU',
        icon: 'swap_horiz',
        action: () => this.toggleDevice(nodeId)
      }
    ];
    
    this.showContextMenu(event.clientX, event.clientY, items, {
      type: 'ml-node',
      data: { nodeId, nodeType }
    });
  }
  
  /**
   * Show context menu for point cloud with ML labels
   */
  showPointCloudContextMenu(event: MouseEvent, point?: { position: number[]; label?: number }): void {
    event.preventDefault();
    event.stopPropagation();
    
    const items: ContextMenuItem[] = [
      {
        id: 'inspect-point',
        label: 'Inspect Point',
        icon: 'center_focus_strong',
        action: () => this.inspectPoint(point)
      },
      {
        id: 'filter-by-class',
        label: point?.label !== undefined ? `Filter by Class ${point.label}` : 'Filter by Class',
        icon: 'filter_alt',
        disabled: point?.label === undefined,
        action: () => this.filterByClass(point?.label)
      },
      {
        id: 'export-region',
        label: 'Export Region',
        icon: 'crop',
        action: () => this.exportRegion(point?.position)
      },
      {
        id: 'separator-1',
        label: '---',
        action: () => {}
      },
      {
        id: 'toggle-labels',
        label: 'Toggle Label Colors',
        icon: 'palette',
        action: () => this.toggleLabels()
      },
      {
        id: 'reset-view',
        label: 'Reset View',
        icon: 'home',
        action: () => this.resetView()
      }
    ];
    
    this.showContextMenu(event.clientX, event.clientY, items, {
      type: 'point-cloud',
      data: point
    });
  }
  
  /**
   * Show generic context menu
   */
  private showContextMenu(x: number, y: number, items: ContextMenuItem[], target?: any): void {
    // Adjust position to keep menu on screen
    const menuWidth = 200;
    const menuHeight = items.filter(item => item.label !== '---').length * 35 + 10;
    
    const adjustedX = Math.min(x, window.innerWidth - menuWidth);
    const adjustedY = Math.min(y, window.innerHeight - menuHeight);
    
    this.menuItems.set(items);
    this.contextMenu.set({
      visible: true,
      x: adjustedX,
      y: adjustedY,
      target
    });
  }
  
  /**
   * Hide context menu
   */
  hideContextMenu(): void {
    this.contextMenu.set({ visible: false, x: 0, y: 0 });
    this.menuItems.set([]);
  }
  
  /**
   * Execute menu item action
   */
  executeAction(itemId: string): void {
    const items = this.menuItems();
    const item = items.find(i => i.id === itemId);
    if (item && !item.disabled) {
      item.action();
      this.hideContextMenu();
    }
  }
  
  // Action implementations
  
  private inspectBoundingBox(box: BoundingBox3D): void {
    console.log('Inspecting bounding box:', box);
    // TODO: Open inspection dialog with box details
  }
  
  private copyCoordinates(box: BoundingBox3D): void {
    const coords = `Center: [${box.center.join(', ')}], Size: [${box.size.join(', ')}], Yaw: ${box.yaw.toFixed(3)}`;
    navigator.clipboard.writeText(coords);
    console.log('Copied coordinates:', coords);
  }
  
  private hideClassType(className: string): void {
    console.log('Hiding class type:', className);
    // TODO: Implement class filtering
  }
  
  private exportBoundingBox(box: BoundingBox3D): void {
    const data = JSON.stringify(box, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `box_${box.id}_${box.label}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  private adjustConfidenceThreshold(currentConfidence: number): void {
    console.log('Adjusting confidence threshold from:', currentConfidence);
    // TODO: Open threshold adjustment dialog
  }
  
  private warmUpModel(nodeId: string): void {
    console.log('Warming up model for node:', nodeId);
    // TODO: Trigger model warm-up
  }
  
  private reloadModel(nodeId: string): void {
    console.log('Reloading model for node:', nodeId);
    // TODO: Reload model
  }
  
  private viewPerformanceMetrics(nodeId: string): void {
    console.log('Viewing performance metrics for node:', nodeId);
    // TODO: Open performance dashboard
  }
  
  private exportNodeConfig(nodeId: string): void {
    console.log('Exporting configuration for node:', nodeId);
    // TODO: Export node configuration
  }
  
  private duplicateNode(nodeId: string): void {
    console.log('Duplicating node:', nodeId);
    // TODO: Duplicate node in flow canvas
  }
  
  private toggleDevice(nodeId: string): void {
    console.log('Toggling device for node:', nodeId);
    // TODO: Switch between CPU and GPU
  }
  
  private inspectPoint(point?: { position: number[]; label?: number }): void {
    console.log('Inspecting point:', point);
    // TODO: Show point details
  }
  
  private filterByClass(labelId?: number): void {
    console.log('Filtering by class:', labelId);
    // TODO: Apply class filter to point cloud
  }
  
  private exportRegion(center?: number[]): void {
    console.log('Exporting region around:', center);
    // TODO: Export point cloud region
  }
  
  private toggleLabels(): void {
    console.log('Toggling label colors');
    // TODO: Toggle point cloud label visualization
  }
  
  private resetView(): void {
    console.log('Resetting view');
    // TODO: Reset camera to default position
  }
}