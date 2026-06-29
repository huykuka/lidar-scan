import {Routes} from '@angular/router';

import {unsavedChangesGuard} from '@core/guards/unsaved-changes.guard';
import {serviceGuard} from '@core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('@layout/main-layout/main-layout.component').then((m) => m.MainLayoutComponent),
    children: [
      {
        path: '',
        redirectTo: 'workspaces',
        pathMatch: 'full',
      },
      {
        path: 'start',
        redirectTo: 'workspaces',
        pathMatch: 'full',
      },
      {
        path: 'workspaces',
        loadComponent: () =>
          import('./features/workspaces/workspaces.component').then((m) => m.WorkspacesComponent),
      },
      {
        path: 'settings',
        canDeactivate: [unsavedChangesGuard],
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
        path: 'node-definitions',
        canActivate: [serviceGuard],
        loadComponent: () =>
          import('./features/admin/admin.component').then((m) => m.AdminComponent),
      },
      {
        path: 'plugins',
        canActivate: [serviceGuard],
        loadComponent: () =>
          import('./features/plugins/plugins.component').then((m) => m.PluginsComponent),
      },
      {
        path: 'logs',
        loadComponent: () => import('./features/logs/logs.component').then((m) => m.LogsComponent),
      },
      {
        path: 'host',
        loadComponent: () => import('./features/host/host.component').then((m) => m.HostComponent),
      },
      {
        path: 'results',
        loadComponent: () =>
          import('./features/results/results-overview/results-overview.component').then(
            (m) => m.ResultsOverviewComponent,
          ),
      },
      {
        path: 'results/:nodeId',
        loadComponent: () =>
          import('./features/results/node-results-list/node-results-list.component').then(
            (m) => m.NodeResultsListComponent,
          ),
      },
      {
        path: 'results/:nodeId/:resultId',
        loadComponent: () =>
          import('./features/results/result-detail/result-detail.component').then(
            (m) => m.ResultDetailComponent,
          ),
      },
      {
        path: 'calibration',
        loadComponent: () =>
          import('./features/calibration/calibration.component').then(
            (m) => m.CalibrationComponent,
          ),
      },
      {
        path: 'calibration/:id',
        loadComponent: () =>
          import('./features/calibration/components/calibration-viewer/calibration-viewer.component').then(
            (m) => m.CalibrationViewerComponent,
          ),
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
