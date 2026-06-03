import {Component, computed, inject, input, output, viewChild} from '@angular/core';

import {NavigationEnd, Router, RouterModule} from '@angular/router';
import {filter} from 'rxjs/operators';
import {SynergyComponentsModule, SynSideNavComponent} from '@synergy-design-system/angular';
import {NAVIGATION_CONFIG} from '@core/models';
import {AuthService, UserRole} from '@core/services/auth.service';

const ROLE_LEVELS: Record<UserRole, number> = {user: 0, admin: 1, service: 2};

@Component({
  selector: 'app-side-nav',
  standalone: true,
  imports: [RouterModule, SynergyComponentsModule],
  templateUrl: './side-nav.component.html',
  styleUrl: './side-nav.component.css',
})
export class SideNavComponent {
  private router = inject(Router);
  private auth = inject(AuthService);

  readonly synSideNav = viewChild.required<SynSideNavComponent>('sideNav');
  open = input<boolean>(true);
  readonly onShow = output<void>();
  readonly onHide = output<void>();
  protected readonly mainNavItems = computed(() => {
    const role = this.auth.user()?.role;
    return NAVIGATION_CONFIG.filter((item) => {
      if (item.footer) return false;
      if (!item.requiredRole) return true;
      if (!role) return false;
      return ROLE_LEVELS[role] >= ROLE_LEVELS[item.requiredRole];
    });
  });
  protected readonly footerNavItems = NAVIGATION_CONFIG.filter((item) => item.footer);

  constructor() {
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      // Auto-close on mobile/tablet (less than 1024px)
      const synSideNav = this.synSideNav();
      if (window.innerWidth < 1024 && synSideNav?.nativeElement?.hide) {
        synSideNav.nativeElement.hide();
      }
    });
  }

  get nativeElement() {
    return this.synSideNav().nativeElement;
  }

  show() {
    const el: any = this.synSideNav()?.nativeElement;
    if (el?.show) el.show();
  }

  hide() {
    const el: any = this.synSideNav()?.nativeElement;
    if (el?.hide) el.hide();
  }
}
