import { Component, signal, ViewChild, AfterViewInit, HostListener, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NavigationService } from '../../core/services/navigation.service';
import { HeaderComponent } from '../components/header/header.component';
import { SideNavComponent } from '../components/side-nav/side-nav.component';
import { FooterComponent } from '../components/footer/footer.component';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [RouterOutlet, CommonModule, HeaderComponent, SideNavComponent, FooterComponent],
  templateUrl: './main-layout.component.html',
  styleUrl: './main-layout.component.css',
})
export class MainLayoutComponent implements AfterViewInit {
  @ViewChild('header') header!: HeaderComponent;
  @ViewChild('sideNav') sideNav!: SideNavComponent;

  private navService = inject(NavigationService);

  protected readonly headline = this.navService.headline;
  protected readonly isSideNavOpen = signal(false);

  private readonly desktopBreakpoint = 1024;
  private autoCollapsedByResize = false;

  ngAfterViewInit() {
    if (this.header && this.sideNav) {
      this.header.nativeElement.connectSideNavigation(this.sideNav.nativeElement);
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
      this.sideNav?.hide?.();
      this.isSideNavOpen.set(false);
      return;
    }

    // Re-open when returning to desktop if we auto-collapsed.
    if (isDesktop && this.autoCollapsedByResize && !this.isSideNavOpen()) {
      this.autoCollapsedByResize = false;
      this.sideNav?.show?.();
      this.isSideNavOpen.set(true);
    }
  }
}
