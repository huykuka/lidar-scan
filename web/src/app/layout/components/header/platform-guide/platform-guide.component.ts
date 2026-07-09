import {ChangeDetectionStrategy, Component, inject} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {DrawerService} from '@core/services/drawer.service';
import {StartGuideDrawerComponent} from '@features/start/start-guide-drawer.component';

@Component({
  selector: 'app-platform-guide',
  imports: [SynergyComponentsModule],
  template: `
    <syn-tooltip content="Platform Guide" [distance]="13">
      <syn-icon-button name="help" label="Platform Guide" size="medium" (click)="toggle()" />
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
export class PlatformGuideComponent {
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
