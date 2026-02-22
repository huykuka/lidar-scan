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
    >
      <syn-button
        variant="text"
        size="small"
        class="wv-btn"
        (click)="clicked.emit()"
        [attr.title]="label()"
      >
        <syn-icon [name]="icon()"></syn-icon>
      </syn-button>
    </div>
  `,
  styles: [
    `
      .wv-btn {
        --syn-button-color-outline: #ffffff;
        --syn-button-color-text: #ffffff;
        color: #ffffff;
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
        color: #ffffff;
      }
    `,
  ],
})
export class WorkspaceViewControlsButtonComponent {
  label = input<string>('');
  icon = input<string>('');
  active = input<boolean>(false);

  clicked = output<void>();
}
