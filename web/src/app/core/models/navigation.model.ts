import {UserRole} from '@core/services/auth.service';

export interface NavItem {
  label: string;
  route: string;
  icon: string;
  divider?: boolean;
  footer?: boolean;
  requiredRole?: UserRole;
}

export const NAVIGATION_CONFIG: NavItem[] = [
  { label: 'Workspaces', route: '/workspaces', icon: 'home', divider: true },
  { label: 'Settings', route: '/settings', icon: 'settings', divider: true, footer: false },
  { label: 'Calibration', route: '/calibration', icon: 'tune', divider: true },
  { label: 'Recordings', route: '/recordings', icon: 'video_library', divider: true },
  { label: 'Results', route: '/results', icon: 'analytics', divider: true },
  {
    label: 'Node Definitions',
    route: '/node-definitions',
    icon: 'extension',
    divider: true,
    footer: true,
    requiredRole: 'service',
  },
  {
    label: 'Plugins',
    route: '/plugins',
    icon: 'deployed_code',
    divider: true,
    footer: true,
    requiredRole: 'service',
  },
  { label: 'Logs', route: '/logs', icon: 'terminal', divider: true, footer: true },
  { label: 'Resource Monitor', route: '/host', icon: 'monitor_heart', divider: true },
];
