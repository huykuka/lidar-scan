import { Routes } from '@angular/router';
import { MainLayoutComponent } from './layout/main-layout/main-layout.component';
import { DevOnlyGuard } from './core/guards/dev-only.guard';

export const routes: Routes = [
  {
    path: '',
    component: MainLayoutComponent,
    children: [
      {
        path: '',
        redirectTo: 'workspaces',
        pathMatch: 'full',
      },
      {
        path: 'start',
        loadComponent: () =>
          import('./features/start/start.component').then((m) => m.StartComponent),
      },
      {
        path: 'workspaces',
        loadComponent: () =>
          import('./features/workspaces/workspaces.component').then((m) => m.WorkspacesComponent),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/settings.component').then((m) => m.SettingsComponent),
      },
      {
        path: 'recordings',
        loadComponent: () =>
          import('./features/recordings/recordings.component').then((m) => m.RecordingsComponent),
      },
      {
        path: 'recordings/:id',
        loadComponent: () =>
          import('./features/recordings/components/recording-viewer/recording-viewer.component').then(
            (m) => m.RecordingViewerComponent,
          ),
      },
      {
        path: 'logs',
        loadComponent: () => import('./features/logs/logs.component').then((m) => m.LogsComponent),
      },
      {
        path: 'calibration',
        loadComponent: () =>
          import('./features/calibration/calibration.component').then((m) => m.CalibrationComponent),
      },
      {
        path: 'calibration/:id',
        loadComponent: () =>
          import('./features/calibration/components/calibration-viewer/calibration-viewer.component').then(
            (m) => m.CalibrationViewerComponent,
          ),
      },
      {
        path: 'dashboard/performance',
        loadComponent: () =>
          import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
        canActivate: [DevOnlyGuard],
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
