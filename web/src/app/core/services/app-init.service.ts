import {Injectable, inject, signal} from '@angular/core';
import {AuthService} from './auth.service';
import {SystemStatusService} from './system-status.service';

@Injectable({providedIn: 'root'})
export class AppInitService {
  private readonly auth = inject(AuthService);
  private readonly systemStatus = inject(SystemStatusService);

  /** True once init() has completed — used to show/hide the loading screen. */
  readonly isReady = signal(false);

  async init(): Promise<void> {
    await this.auth.verifyToken();
    this.systemStatus.start();
    this.isReady.set(true);
  }
}
