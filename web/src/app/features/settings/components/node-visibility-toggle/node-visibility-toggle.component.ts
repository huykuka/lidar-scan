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
    this.visibilityChanged.emit(!this.node().visible);
  }

  protected getButtonClasses(): string {
    const baseClasses = 'text-white';
    
    if (this.isPending()) {
      return `${baseClasses} opacity-50 cursor-not-allowed`;
    }
    
    if (this.node().visible === false) {
      return `${baseClasses} opacity-40`;
    }
    
    return baseClasses;
  }
}
