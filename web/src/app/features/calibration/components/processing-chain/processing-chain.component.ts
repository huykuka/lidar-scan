import {Component, input} from '@angular/core';
import {CommonModule} from '@angular/common';
import {SynergyComponentsModule} from '@synergy-design-system/angular';

/**
 * Component for visualizing the processing chain of a calibration result.
 * Displays the ordered list of DAG nodes from source sensor to calibration node.
 * 
 * Example rendering:
 * [Sensor A] → [Crop] → [Downsample] → [Calibration]
 */
@Component({
  selector: 'app-processing-chain',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  templateUrl: './processing-chain.component.html',
})
export class ProcessingChainComponent {
  /**
   * Ordered list of node IDs from source sensor to calibration node
   */
  processingChain = input.required<string[]>();

  /**
   * Display mode: 'full' shows all nodes with arrows, 'compact' shows count badge
   */
  displayMode = input<'full' | 'compact'>('full');

  /**
   * Whether to show the last node (calibration node) in the chain
   */
  showLastNode = input<boolean>(true);

  /**
   * Get the display chain based on showLastNode setting
   */
  getDisplayChain(): string[] {
    const chain = this.processingChain();
    if (!this.showLastNode() && chain.length > 1) {
      return chain.slice(0, -1);
    }
    return chain;
  }

  /**
   * Get a shortened node ID for display
   */
  getNodeDisplayName(nodeId: string): string {
    // Extract last 8 characters if it looks like a UUID
    if (nodeId.length > 20 && nodeId.includes('-')) {
      return '...' + nodeId.slice(-8);
    }
    return nodeId;
  }
}
