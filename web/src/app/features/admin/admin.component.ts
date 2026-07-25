import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NavigationService } from '@core/services';
import { NodeTypesListComponent } from './components/node-types-list/node-types-list.component';
import { PluginsListComponent } from './components/plugins-list/plugins-list.component';

@Component({
  selector: 'app-admin',
  imports: [SynergyComponentsModule, NodeTypesListComponent, PluginsListComponent],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AdminComponent implements OnInit {
  private navService = inject(NavigationService);
  protected activeSection = signal<'node-types' | 'plugins'>('node-types');

  ngOnInit() {
    this.navService.setPageConfig({
      title: 'Node Definitions & Plugins',
      subtitle: 'Manage node types and extensions',
    });
  }

  protected onTabShow(event: Event) {
    const panel = (event as CustomEvent).detail?.name as 'node-types' | 'plugins';
    if (panel) this.activeSection.set(panel);
  }
}
