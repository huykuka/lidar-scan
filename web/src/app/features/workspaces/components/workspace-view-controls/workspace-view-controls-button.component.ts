import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-workspace-view-controls-button',
  standalone: true,
  imports: [CommonModule, SynergyComponentsModule],
  template: `
    <div
      class="rounded-xl transition-colors"
      [class.bg-white/10]="active()"
      [class.hover:bg-white/10]="!active()"
      [class.hover:bg-red-500/20]="danger()"
      [style.color]="danger() ? 'var(--syn-color-danger-600)' : 'white'"
    >
      <syn-button
        variant="text"
        size="small"
        class="wv-btn"
        (click)="clicked.emit()"
        [attr.title]="label()"
      >
        <syn-icon [attr.name]="icon()"></syn-icon>
      </syn-button>
    </div>
  `,
  styles: [
    `
      .wv-btn {
        --syn-button-color-text: white;
      }

      :host ::ng-deep .button--text {
        color: #f2f0ed;
      }

      /* Icon-only button: make padding visually square/centered.
         (Part names depend on Synergy's web component implementation; harmless if unsupported.) */
      .wv-btn::part(button),
      .wv-btn::part(base),
      .wv-btn::part(control) {
        padding: 6px;
        min-width: 32px;
      }

      .wv-btn syn-icon {
        color: inherit;
      }
    `,
  ],
})
export class WorkspaceViewControlsButtonComponent {
  label = input<string>('');
  icon = input<string>('');
  active = input<boolean>(false);
  danger = input<boolean>(false);

  clicked = output<void>();
}
