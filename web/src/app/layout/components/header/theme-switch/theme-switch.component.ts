import {ChangeDetectionStrategy, Component, computed, inject} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ThemeService} from '@core/services/theme.service';

/**
 * Self-contained theme toggle button for the app header.
 * Reads and writes ThemeService; renders a single syn-icon-button
 * that swaps between light_mode / dark_mode icons.
 */
@Component({
  selector: 'app-theme-switch',
  imports: [SynergyComponentsModule],
  template: `
    <syn-tooltip content="Switch theme" [distance]="13">
      <syn-icon-button [name]="icon()" [label]="label()" size="medium" (click)="toggle()" />
    </syn-tooltip>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
    }
  `,
})
export class ThemeSwitchComponent {
  private readonly themeService = inject(ThemeService);

  protected readonly isDark = computed(() => this.themeService.theme() === 'dark');

  protected readonly icon = computed(() => (this.isDark() ? 'light_mode_fill' : 'dark_mode'));

  protected readonly label = computed(() =>
    this.isDark() ? 'Switch to light mode' : 'Switch to dark mode',
  );

  protected toggle(): void {
    this.themeService.toggle();
  }
}
