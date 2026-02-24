import { Component, EventEmitter, Output, input, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { SynergyComponentsModule, SynSideNavComponent } from '@synergy-design-system/angular';
import { NavItem, NAVIGATION_CONFIG } from '../../../core/models/navigation.model';

@Component({
  selector: 'app-side-nav',
  standalone: true,
  imports: [CommonModule, RouterModule, SynergyComponentsModule],
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

  protected readonly mainNavItems = NAVIGATION_CONFIG.filter((item) => !item.footer);
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
