import { Component, inject, OnInit } from '@angular/core';
import { NavigationService } from '../../core/services/navigation.service';

@Component({
  selector: 'app-start',
  standalone: true,
  templateUrl: './start.component.html',
  styleUrl: './start.component.css',
})
export class StartComponent implements OnInit {
  private navService = inject(NavigationService);

  ngOnInit() {
    this.navService.setHeadline('Start');
  }
}
