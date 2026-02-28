export interface NavItem {
  label: string;
  route: string;
  icon: string;
  divider?: boolean;
  footer?: boolean;
}

export const NAVIGATION_CONFIG: NavItem[] = [
  { label: 'Start', route: '/start', icon: 'home' },
  { label: 'Workspaces', route: '/workspaces', icon: 'spoke', divider: true },
  { label: 'Settings', route: '/settings', icon: 'settings', divider: true, footer: false },
  { label: 'Calibration', route: '/calibration', icon: 'tune', divider: true },
  { label: 'Recordings', route: '/recordings', icon: 'video_library', divider: true },
  { label: 'Logs', route: '/logs', icon: 'description', divider: true },
];
