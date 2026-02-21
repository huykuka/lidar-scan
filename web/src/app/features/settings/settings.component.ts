import { Component, inject, OnInit } from '@angular/core';
import { NavigationService } from '../../core/services/navigation.service';
import { SynergyComponentsModule } from '@synergy-design-system/angular';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
  imports: [SynergyComponentsModule],
})
export class SettingsComponent implements OnInit {
  private navService = inject(NavigationService);

  ngOnInit() {
    this.navService.setHeadline('Settings');
  }
}
