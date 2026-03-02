import { Component, EventEmitter, Output, input, ViewChild, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { SynSideNavComponent } from '@synergy-design-system/angular';
import { NavItem, NAVIGATION_CONFIG } from '../../../core/models/navigation.model';
import { environment } from '../../../../environments/environment';

@Component({
  selector: 'app-side-nav',
  standalone: true,
  imports: [CommonModule, RouterModule, SynSideNavComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './side-nav.component.html',
  styleUrl: './side-nav.component.css',
})
export class SideNavComponent {
  @ViewChild('sideNav', { static: true }) synSideNav!: SynSideNavComponent;
  open = input<boolean>(true);
  @Output() onShow = new EventEmitter<void>();
  @Output() onHide = new EventEmitter<void>();

  get nativeElement() {
    return this.synSideNav.nativeElement;
  }

  show() {
    const el: any = this.synSideNav?.nativeElement;
    if (el?.show) el.show();
  }

  hide() {
    const el: any = this.synSideNav?.nativeElement;
    if (el?.hide) el.hide();
  }

  protected readonly mainNavItems = NAVIGATION_CONFIG.filter((item) => {
    if (!item.footer) {
      // Hide Performance dashboard in production builds
      if (environment.production && item.route === '/dashboard/performance') {
        return false;
      }
      return true;
    }
    return false;
  });
  protected readonly footerNavItems = NAVIGATION_CONFIG.filter((item) => item.footer);

  constructor(private router: Router) {
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      // Auto-close on mobile/tablet (less than 1024px)
      if (window.innerWidth < 1024 && this.synSideNav?.nativeElement?.hide) {
        this.synSideNav.nativeElement.hide();
      }
    });
  }
}
