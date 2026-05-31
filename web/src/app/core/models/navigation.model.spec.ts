import {NAVIGATION_CONFIG, NavItem} from './navigation.model';
import {UserRole} from '@core/services/auth.service';

describe('NAVIGATION_CONFIG', () => {
  it('should contain Node Definitions nav item', () => {
    const nodeDefs = NAVIGATION_CONFIG.find((item) => item.label === 'Node Definitions');
    expect(nodeDefs).toBeDefined();
    expect(nodeDefs!.route).toBe('/node-definitions');
  });

  it('should require service role for Node Definitions', () => {
    const nodeDefs = NAVIGATION_CONFIG.find((item) => item.label === 'Node Definitions')!;
    expect(nodeDefs.requiredRole).toBe('service');
  });

  it('should not require a role for standard nav items', () => {
    const standardItems = ['Start', 'Workspaces', 'Settings', 'Logs'];
    for (const label of standardItems) {
      const item = NAVIGATION_CONFIG.find((i) => i.label === label);
      expect(item).toBeDefined();
      expect(item!.requiredRole).toBeUndefined();
    }
  });

  function visibleItems(role: UserRole | null): NavItem[] {
    return NAVIGATION_CONFIG.filter((item) => {
      if (!item.requiredRole) return true;
      if (!role) return false;
      const levels: Record<UserRole, number> = {user: 0, admin: 1, service: 2};
      return role === item.requiredRole || levels[role] >= levels[item.requiredRole];
    });
  }

  it('guest sees all items except Node Definitions', () => {
    const items = visibleItems(null);
    const labels = items.map((i) => i.label);
    expect(labels).not.toContain('Node Definitions');
    expect(labels).toContain('Settings');
    expect(labels).toContain('Logs');
  });

  it('user role sees all items except Node Definitions', () => {
    const items = visibleItems('user');
    expect(items.map((i) => i.label)).not.toContain('Node Definitions');
  });

  it('admin role sees all items except Node Definitions', () => {
    const items = visibleItems('admin');
    expect(items.map((i) => i.label)).not.toContain('Node Definitions');
  });

  it('service role sees all items including Node Definitions', () => {
    const items = visibleItems('service');
    expect(items.map((i) => i.label)).toContain('Node Definitions');
  });
});
