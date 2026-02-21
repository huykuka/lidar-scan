import { Component, inject, OnInit } from '@angular/core';
import { NavigationService } from '../../core/services/navigation.service';

@Component({
  selector: 'app-workspaces',
  standalone: true,
  templateUrl: './workspaces.component.html',
  styleUrl: './workspaces.component.css',
})
export class WorkspacesComponent implements OnInit {
  private navService = inject(NavigationService);

  ngOnInit() {
    this.navService.setHeadline('Workspaces');
  }
}
