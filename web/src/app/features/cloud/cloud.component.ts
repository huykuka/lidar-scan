import { Component, inject, OnInit } from '@angular/core';
import { NavigationService } from '../../core/services/navigation.service';

@Component({
  selector: 'app-cloud',
  standalone: true,
  template: `
    <div class="p-4">
      <p>Synchronize your data with Synergy Cloud services.</p>
    </div>
  `,
})
export class CloudComponent implements OnInit {
  private navService = inject(NavigationService);

  ngOnInit() {
    this.navService.setHeadline('Cloud');
  }
}
