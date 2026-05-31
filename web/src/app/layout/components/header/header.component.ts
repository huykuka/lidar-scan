import {Component, inject, input, signal, viewChild} from '@angular/core';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {SynergyComponentsModule, SynergyFormsModule, SynHeaderComponent} from '@synergy-design-system/angular';
import {SystemStatusService} from '../../../core/services/system-status.service';
import {NavigationService} from '../../../core/services/navigation.service';
import {AuthService} from '../../../core/services/auth.service';
import {ConnectionStatusComponent} from './connection-status/connection-status.component';
import {SensorStatusComponent} from './sensor-status/sensor-status.component';
import {NoticesStatusComponent} from './notices-status/notices-status.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    SynergyComponentsModule,
    SynergyFormsModule,
    ConnectionStatusComponent,
    SensorStatusComponent,
    NoticesStatusComponent,
  ],
  templateUrl: './header.component.html',
  styleUrl: './header.component.css',
})
export class HeaderComponent {
  label = input<string>('Lidar 3D Control Cockpit');
  readonly synHeader = viewChild.required<SynHeaderComponent>('header');

  private readonly systemStatus = inject(SystemStatusService);
  private readonly navService = inject(NavigationService);
  protected readonly auth = inject(AuthService);

  protected readonly currentPage = this.navService.headline;

  protected readonly loginForm = new FormGroup({
    username: new FormControl('', [Validators.required]),
    password: new FormControl('', [Validators.required]),
  });
  protected readonly loginLoading = signal(false);
  protected readonly loginError = signal<string | null>(null);

  get nativeElement() {
    return this.synHeader().nativeElement;
  }

  protected onRefresh(): void {
    this.systemStatus.refreshNow();
  }

  protected onAcknowledge(): void {
    this.systemStatus.acknowledge();
  }

  protected async onLogin(): Promise<void> {
    if (this.loginForm.invalid) return;

    const {username, password} = this.loginForm.getRawValue();
    this.loginLoading.set(true);
    this.loginError.set(null);

    try {
      await this.auth.login(username!, password!);
      this.loginForm.reset();
    } catch {
      this.loginError.set('Invalid credentials.');
    } finally {
      this.loginLoading.set(false);
    }
  }

  protected onLogout(): void {
    this.auth.logout();
  }
}
