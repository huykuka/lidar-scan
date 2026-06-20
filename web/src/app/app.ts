import {Component, inject} from '@angular/core';
import {RouterOutlet} from '@angular/router';
import {AppInitService} from './core/services/app-init.service';
import {LoadingScreenComponent} from './layout/loading-screen/loading-screen.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, LoadingScreenComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly isReady = inject(AppInitService).isReady;
}
