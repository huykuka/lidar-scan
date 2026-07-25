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
  { label: 'Workspaces', route: '/workspaces', icon: 'home_fill', divider: false },
  {
    label: 'Settings',
    route: '/settings',
    icon: 'account_tree_fill',
    divider: true,
    footer: false,
  },
  { label: 'Calibration', route: '/calibration', icon: 'tune_fill', divider: true },
  { label: 'Recordings', route: '/recordings', icon: 'video_library_fill', divider: true },
  { label: 'Results', route: '/results', icon: 'analytics_fill', divider: true },
  {
    label: 'Node Definitions & Plugins',
    route: '/node-definitions',
    icon: 'deployed_code_fill',
    footer: true,
    requiredRole: 'service',
  },
  { label: 'Logs', route: '/logs', icon: 'terminal_fill', divider: true, footer: true },
  { label: 'Resource Monitor', route: '/host', icon: 'monitor_heart_fill', divider: true },
];
