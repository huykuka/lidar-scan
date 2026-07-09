import {ChangeDetectionStrategy, Component, computed, inject, input, viewChild} from '@angular/core';
import {SynergyComponentsModule, SynHeaderComponent} from '@synergy-design-system/angular';
import {SystemStatusService} from '../../../core/services/system-status.service';
import {NavigationService} from '../../../core/services/navigation.service';
import {ConnectionStatusComponent} from './connection-status/connection-status.component';
import {SensorStatusComponent} from './sensor-status/sensor-status.component';
import {UserInfoComponent} from './user-info/user-info.component';
import {ThemeSwitchComponent} from './theme-switch/theme-switch.component';
import {PlatformGuideComponent} from './platform-guide/platform-guide.component';
import packageJson from '../../../../../package.json';

@Component({
  selector: 'app-header',
  imports: [
    SynergyComponentsModule,
    ConnectionStatusComponent,
    SensorStatusComponent,
    UserInfoComponent,
    ThemeSwitchComponent,
    PlatformGuideComponent,
  ],
  templateUrl: './header.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './header.component.css',
})
export class HeaderComponent {
  label = input<string>('Lidar 3D Control Cockpit');
  protected readonly uiVersion: string = packageJson.version;

  readonly synHeader = viewChild.required<SynHeaderComponent>('header');

  private readonly systemStatus = inject(SystemStatusService);
  private readonly navService = inject(NavigationService);

  protected readonly headline = this.navService.headline;
  protected readonly subtitle = this.navService.subtitle;
  protected readonly currentPage = this.navService.headline;

  /**
   * When there is no headline (no slot override), drive the label attribute directly.
   * This keeps syn-header's native single-line label rendering — no flex div, no wrapping.
   * When a headline exists, the label slot overrides it with the full breadcrumb.
   */
  protected readonly headerLabel = computed(() =>
    this.headline() ? '' : `${this.label()} v${this.uiVersion}`,
  );

  get nativeElement() {
    return this.synHeader().nativeElement;
  }

  protected onRefresh(): void {
    this.systemStatus.refreshNow();
  }

  protected onAcknowledge(): void {
    this.systemStatus.acknowledge();
  }
}
