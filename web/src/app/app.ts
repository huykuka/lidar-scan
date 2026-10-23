import {ChangeDetectionStrategy, Component, inject} from '@angular/core';
import {RouterOutlet} from '@angular/router';
import {EmbedService} from './core/services/embed.service';
import {AppInitService} from './core/services/app-init.service';
import {LoadingScreenComponent} from './layout/loading-screen/loading-screen.component';
import {DrawerHostComponent} from './shared/components/drawer-host/drawer-host.component';
import {DialogHostComponent} from './shared/components/dialog-host/dialog-host.component';
import {OnboardingComponent} from './shared/components/onboarding/onboarding.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, LoadingScreenComponent, DrawerHostComponent, DialogHostComponent, OnboardingComponent],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './app.scss',
})
export class App {
  readonly isReady = inject(AppInitService).isReady;
  protected readonly embed = inject(EmbedService);
}
