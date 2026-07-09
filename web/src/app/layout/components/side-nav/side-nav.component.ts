import {
  ChangeDetectionStrategy,
  Component,
  computed,
  HostListener,
  inject,
  input,
  OnInit,
  output,
  signal,
  viewChild,
} from '@angular/core';

import {NavigationEnd, Router, RouterModule} from '@angular/router';
import {filter} from 'rxjs/operators';
import {SynergyComponentsModule, SynSideNavComponent} from '@synergy-design-system/angular';
import {NAVIGATION_CONFIG} from '@core/models';
import {AuthService, UserRole} from '@core/services/auth.service';

const ROLE_LEVELS: Record<UserRole, number> = {user: 0, admin: 1, service: 2};
const DESKTOP_BREAKPOINT = 1024;

@Component({
  selector: 'app-side-nav',
  imports: [RouterModule, SynergyComponentsModule],
  templateUrl: './side-nav.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './side-nav.component.css',
})
export class SideNavComponent implements OnInit {
  private router = inject(Router);
  private auth = inject(AuthService);

  readonly synSideNav = viewChild.required<SynSideNavComponent>('sideNav');
  open = input<boolean>(true);
  readonly onShow = output<void>();
  readonly onHide = output<void>();

  /** 'sticky' on desktop (≥1024px), 'default' on mobile — drives grayout overlay on mobile */
  protected readonly variant = signal<'default' | 'sticky'>(
    window.innerWidth >= DESKTOP_BREAKPOINT ? 'sticky' : 'default',
  );

  /** noFocusTrapping only makes sense for sticky (desktop) */
  protected readonly noFocusTrapping = computed(() => this.variant() === 'sticky');

  protected readonly mainNavItems = computed(() => {
    const role = this.auth.user()?.role;
    return NAVIGATION_CONFIG.filter((item) => {
      if (item.footer) return false;
      if (!item.requiredRole) return true;
      if (!role) return false;
      return ROLE_LEVELS[role] >= ROLE_LEVELS[item.requiredRole];
    });
  });

  protected readonly footerNavItems = computed(() => {
    const role = this.auth.user()?.role;
    return NAVIGATION_CONFIG.filter((item) => {
      if (!item.footer) return false;
      if (!item.requiredRole) return true;
      if (!role) return false;
      return ROLE_LEVELS[role] >= ROLE_LEVELS[item.requiredRole];
    });
  });

  ngOnInit(): void {
    // Auto-close on mobile after navigation
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      if (window.innerWidth < DESKTOP_BREAKPOINT) {
        this.synSideNav()?.nativeElement?.hide?.();
      }
    });
  }

  @HostListener('window:resize')
  protected onWindowResize(): void {
    this.variant.set(window.innerWidth >= DESKTOP_BREAKPOINT ? 'sticky' : 'default');
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
