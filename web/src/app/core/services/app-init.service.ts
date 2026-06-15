import {Injectable, inject} from '@angular/core';
import {AuthService} from './auth.service';
import {SystemStatusService} from './system-status.service';

@Injectable({providedIn: 'root'})
export class AppInitService {
  private readonly auth = inject(AuthService);
  private readonly systemStatus = inject(SystemStatusService);

  async init(): Promise<void> {
    await this.auth.verifyToken();
    this.systemStatus.start();
  }
}
