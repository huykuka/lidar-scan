import { Component, input, output } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeConfig } from '../../../../core/models/node.model';

@Component({
  selector: 'app-node-visibility-toggle',
  imports: [SynergyComponentsModule],
  templateUrl: './node-visibility-toggle.component.html',
  styleUrl: './node-visibility-toggle.component.css',
})
export class NodeVisibilityToggleComponent {
  node = input.required<NodeConfig>();
  isPending = input<boolean>(false);
  visibilityChanged = output<boolean>();

  protected onToggle(): void {
    // Ensure we handle the optional/undefined visible case properly
    const currentVisible = this.node().visible !== false; // defaults to true if undefined/null
    this.visibilityChanged.emit(!currentVisible);
  }

  protected getTooltipText(): string {
    const nodeName = this.node().name || 'Node';
    return this.node().visible !== false ? `Hide ${nodeName}` : `Show ${nodeName}`;
  }

  protected getAriaLabel(): string {
    const nodeName = this.node().name || 'Node';
    return this.node().visible !== false ? `Hide node ${nodeName}` : `Show node ${nodeName}`;
  }
}
