import { Routes } from '@angular/router';
import { MainLayoutComponent } from './layout/main-layout/main-layout.component';

export const routes: Routes = [
  {
    path: '',
    component: MainLayoutComponent,
    children: [
      {
        path: '',
        redirectTo: 'start',
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
        path: 'logs',
        loadComponent: () =>
          import('./features/logs/logs.component').then((m) => m.LogsComponent),
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
