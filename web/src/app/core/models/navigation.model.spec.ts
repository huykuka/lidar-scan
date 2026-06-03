import {NAVIGATION_CONFIG, NavItem} from './navigation.model';
import {UserRole} from '@core/services/auth.service';

const ROLE_LEVELS: Record<UserRole, number> = {user: 0, admin: 1, service: 2};

function visibleItems(role: UserRole | undefined): NavItem[] {
  return NAVIGATION_CONFIG.filter((item) => {
    if (item.footer) return false;
    if (!item.requiredRole) return true;
    if (!role) return false;
    return ROLE_LEVELS[role] >= ROLE_LEVELS[item.requiredRole];
  });
}

describe('NAVIGATION_CONFIG', () => {
  it('should have Node Definitions with requiredRole service', () => {
    const nodeDef = NAVIGATION_CONFIG.find((i) => i.label === 'Node Definitions');
    expect(nodeDef).toBeTruthy();
    expect(nodeDef!.requiredRole).toBe('service');
  });

  it('guest (no role) should not see Node Definitions', () => {
    const labels = visibleItems(undefined).map((i) => i.label);
    expect(labels).not.toContain('Node Definitions');
  });

  it('user role should not see Node Definitions', () => {
    const labels = visibleItems('user').map((i) => i.label);
    expect(labels).not.toContain('Node Definitions');
  });

  it('admin role should not see Node Definitions (requires service)', () => {
    const labels = visibleItems('admin').map((i) => i.label);
    expect(labels).not.toContain('Node Definitions');
  });

  it('service role should see Node Definitions', () => {
    const labels = visibleItems('service').map((i) => i.label);
    expect(labels).toContain('Node Definitions');
  });

  it('all non-restricted items visible to every role', () => {
    const unrestricted = NAVIGATION_CONFIG.filter((i) => !i.footer && !i.requiredRole);
    for (const role of ['user', 'admin', 'service'] as UserRole[]) {
      const visible = visibleItems(role);
      for (const item of unrestricted) {
        expect(visible).toContain(item);
      }
    }
  });

  it('should have expected number of main nav items', () => {
    const mainItems = NAVIGATION_CONFIG.filter((i) => !i.footer);
    expect(mainItems.length).toBe(8);
  });
});
