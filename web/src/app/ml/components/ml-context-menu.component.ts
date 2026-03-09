// ML Context Menu Component
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MLContextMenuService } from '../services/ml-context-menu.service';

@Component({
  selector: 'app-ml-context-menu',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ml-context-menu.component.html',
  styleUrls: ['./ml-context-menu.component.css']
})
export class MLContextMenuComponent {
  
  constructor(
    public contextMenuService: MLContextMenuService
  ) {}
  
  /**
   * Execute menu action
   */
  executeAction(itemId: string): void {
    this.contextMenuService.executeAction(itemId);
  }
}