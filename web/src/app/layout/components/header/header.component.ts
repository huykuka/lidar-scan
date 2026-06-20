import {Component, inject, input, viewChild} from '@angular/core';
import {SynergyComponentsModule, SynHeaderComponent} from '@synergy-design-system/angular';
import {SystemStatusService} from '../../../core/services/system-status.service';
import {NavigationService} from '../../../core/services/navigation.service';
import {ConnectionStatusComponent} from './connection-status/connection-status.component';
import {SensorStatusComponent} from './sensor-status/sensor-status.component';
import {NoticesStatusComponent} from './notices-status/notices-status.component';
import {UserInfoComponent} from './user-info/user-info.component';
import {ThemeSwitchComponent} from './theme-switch/theme-switch.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    SynergyComponentsModule,
    ConnectionStatusComponent,
    SensorStatusComponent,
    NoticesStatusComponent,
    UserInfoComponent,
    ThemeSwitchComponent,
  ],
  templateUrl: './header.component.html',
  styleUrl: './header.component.css',
})
export class HeaderComponent {
  label = input<string>('Lidar 3D Control Cockpit');
  readonly synHeader = viewChild.required<SynHeaderComponent>('header');

  private readonly systemStatus = inject(SystemStatusService);
  private readonly navService = inject(NavigationService);

  protected readonly currentPage = this.navService.headline;

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
