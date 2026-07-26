import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { ThemeService } from '@core/services/theme.service';

/**
 * Self-contained theme toggle button for the app header.
 * Reads and writes ThemeService; renders a single syn-icon-button
 * that swaps between light_mode / dark_mode icons.
 */
@Component({
  selector: 'app-theme-switch',
  imports: [SynergyComponentsModule],
  template: `
    @if (mobile()) {
      <div
        class="flex w-full items-center gap-2 py-0.5 pl-1 pr-3 cursor-pointer transition-colors duration-150 hover:bg-syn-color-neutral-100"
        (click)="toggle()"
      >
        <syn-icon-button [name]="icon()" [label]="label()" size="medium" />
        <span class="text-sm font-medium text-syn-color-neutral-700 select-none">Theme</span>
      </div>
    } @else {
      <syn-tooltip content="Switch theme" [distance]="13">
        <syn-icon-button [name]="icon()" [label]="label()" size="medium" (click)="toggle()" />
      </syn-tooltip>
    }
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
  readonly mobile = input(false);
  private readonly themeService = inject(ThemeService);

  protected readonly isDark = computed(() => this.themeService.theme() === 'dark');

  protected readonly icon = computed(() => (this.isDark() ? 'light_mode' : 'dark_mode_fill'));

  protected readonly label = computed(() =>
    this.isDark() ? 'Switch to light mode' : 'Switch to dark mode',
  );

  protected toggle(): void {
    this.themeService.toggle();
  }
}
