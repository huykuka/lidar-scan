import {Component, inject, ChangeDetectionStrategy} from '@angular/core';
import {RouterOutlet} from '@angular/router';
import {AppInitService} from './core/services/app-init.service';
import {LoadingScreenComponent} from './layout/loading-screen/loading-screen.component';
import {DrawerHostComponent} from './shared/components/drawer-host/drawer-host.component';
import {DialogHostComponent} from './shared/components/dialog-host/dialog-host.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, LoadingScreenComponent, DrawerHostComponent, DialogHostComponent],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.css',
})
export class App {
  readonly isReady = inject(AppInitService).isReady;
}
