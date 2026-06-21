import {Injectable, inject, signal} from '@angular/core';
import {AuthService} from './auth.service';
import {SystemStatusService} from './system-status.service';
import {ThemeService} from './theme.service';

@Injectable({providedIn: 'root'})
export class AppInitService {
  private readonly auth = inject(AuthService);
  private readonly systemStatus = inject(SystemStatusService);
  private readonly themeService = inject(ThemeService);

  /** True once init() has completed — used to show/hide the loading screen. */
  readonly isReady = signal(false);

  async init(): Promise<void> {
    this.themeService.checkTheme();
    await this.auth.verifyToken();
    this.systemStatus.start();
    this.isReady.set(true);
  }
}
