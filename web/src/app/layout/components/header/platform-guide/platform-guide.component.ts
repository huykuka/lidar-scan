import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { DrawerService } from '@core/services/drawer.service';
import { StartGuideDrawerComponent } from '@features/start/start-guide-drawer.component';

@Component({
  selector: 'app-platform-guide',
  imports: [SynergyComponentsModule],
  template: `
    @if (mobile()) {
      <div
        class="flex w-full items-center gap-2 py-0.5 pl-1 pr-3 cursor-pointer transition-colors duration-150 hover:bg-syn-color-neutral-100"
        (click)="toggle()"
      >
        <syn-icon-button name="help" label="Platform Guide" size="medium" />
        <span class="text-sm font-medium text-syn-color-neutral-700 select-none"
          >Platform Guide</span
        >
      </div>
    } @else {
      <syn-tooltip content="Platform Guide" [distance]="13">
        <syn-icon-button name="help" label="Platform Guide" size="medium" (click)="toggle()" />
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
export class PlatformGuideComponent {
  readonly mobile = input(false);
  private readonly drawer = inject(DrawerService);

  protected toggle(): void {
    const isOpen = this.drawer.isOpen() && this.drawer.component() === StartGuideDrawerComponent;
    if (isOpen) {
      this.drawer.close();
      return;
    }

    this.drawer.open(StartGuideDrawerComponent, {
      title: 'Platform Guide',
      size: 'min(980px, 92vw)',
      placement: 'end',
      showFooter: false,
    });
  }
}
