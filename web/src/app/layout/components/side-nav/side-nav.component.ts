import { Component, EventEmitter, Output, input, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
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

  protected readonly mainNavItems = NAVIGATION_CONFIG.filter((item) => !item.footer);
  protected readonly footerNavItems = NAVIGATION_CONFIG.filter((item) => item.footer);
}
