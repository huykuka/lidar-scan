import {AfterViewInit, Component, HostListener, inject, signal, viewChild} from '@angular/core';
import {ChildrenOutletContexts, RouterOutlet} from '@angular/router';

import {NavigationService} from '@core/services';
import {HeaderComponent} from '../components/header/header.component';
import {SideNavComponent} from '../components/side-nav/side-nav.component';
import {FooterComponent} from '../components/footer/footer.component';
import {pageTransition} from '@core/animations/page-transitions';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [RouterOutlet, HeaderComponent, SideNavComponent, FooterComponent],
  templateUrl: './main-layout.component.html',
  styleUrl: './main-layout.component.css',
  animations: [pageTransition],
})
export class MainLayoutComponent implements AfterViewInit {
  readonly header = viewChild.required<HeaderComponent>('header');
  readonly sideNav = viewChild.required<SideNavComponent>('sideNav');
  protected readonly isSideNavOpen = signal(false);
  private navService = inject(NavigationService);
  protected readonly headline = this.navService.headline;
  protected readonly subtitle = this.navService.subtitle;
  protected readonly showActionsSlot = this.navService.showActionsSlot;
  private contexts = inject(ChildrenOutletContexts);
  private readonly desktopBreakpoint = 1024;
  private autoCollapsedByResize = false;

  getRouteAnimationData() {
    return this.contexts.getContext('primary')?.route?.snapshot?.url.join('/') || 'root';
  }

  ngAfterViewInit() {
    const header = this.header();
    const sideNav = this.sideNav();
    if (header && sideNav) {
      header.nativeElement.connectSideNavigation(sideNav.nativeElement);
    }

    // Initial state based on viewport.
    this.applyResponsiveLayout();
  }

  protected handleSideNavShow() {
    this.isSideNavOpen.set(true);
  }

  protected handleSideNavHide() {
    this.isSideNavOpen.set(false);
  }

  @HostListener('window:resize')
  protected onWindowResize() {
    this.applyResponsiveLayout();
  }

  private applyResponsiveLayout() {
    const isDesktop = window.innerWidth >= this.desktopBreakpoint;

    // Collapse when entering mobile/tablet.
    if (!isDesktop && this.isSideNavOpen()) {
      this.autoCollapsedByResize = true;
      this.sideNav()?.hide?.();
      this.isSideNavOpen.set(false);
      return;
    }

    // Re-open when returning to desktop if we auto-collapsed.
    if (isDesktop && this.autoCollapsedByResize && !this.isSideNavOpen()) {
      this.autoCollapsedByResize = false;
      this.sideNav()?.show?.();
      this.isSideNavOpen.set(true);
    }
  }
}
