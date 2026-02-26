import { Component, inject, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { NavigationService } from '../../core/services/navigation.service';
import { SynIconComponent } from '@synergy-design-system/angular';

@Component({
  selector: 'app-start',
  standalone: true,
  templateUrl: './start.component.html',
  styleUrl: './start.component.css',
  imports: [SynIconComponent],
})
export class StartComponent implements OnInit {
  private navService = inject(NavigationService);
  private router = inject(Router);

  ngOnInit() {
    this.navService.setPageConfig({
      title: 'Start',
      subtitle: 'Welcome to the LiDAR Command Surface',
    });
  }

  navigateTo(route: string) {
    this.router.navigate([route]);
  }
}
