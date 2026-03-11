import {Component, inject, input, output, viewChild} from '@angular/core';

import {NavigationEnd, Router, RouterModule} from '@angular/router';
import {filter} from 'rxjs/operators';
import {SynergyComponentsModule, SynSideNavComponent} from '@synergy-design-system/angular';
import {NAVIGATION_CONFIG} from '@core/models';

@Component({
  selector: 'app-side-nav',
  standalone: true,
  imports: [RouterModule, SynergyComponentsModule],
  templateUrl: './side-nav.component.html',
  styleUrl: './side-nav.component.css',
})
export class SideNavComponent {
  private router = inject(Router);

  readonly synSideNav = viewChild.required<SynSideNavComponent>('sideNav');
  open = input<boolean>(true);
  readonly onShow = output<void>();
  readonly onHide = output<void>();
  protected readonly mainNavItems = NAVIGATION_CONFIG.filter((item) => !item.footer);
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
