import { Component, inject, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { Router } from '@angular/router';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { ResultsApiService, MOCK_NODE_INDEX } from '@core/services/api/results-api.service';
import { NavigationService } from '@core/services';
import { NodeResultSummary } from '@core/models';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-results-overview',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './results-overview.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './results-overview.component.css',
})
export class ResultsOverviewComponent implements OnInit {
  protected nodes = signal<NodeResultSummary[]>([]);
  protected isLoading = signal(false);
  protected error = signal<string | null>(null);

  private resultsApi = inject(ResultsApiService);
  private navService = inject(NavigationService);
  private router = inject(Router);

  ngOnInit(): void {
    this.navService.setPageConfig({
      title: 'Results',
      subtitle: 'Browse stored results from Result Storage nodes',
    });
    void this.loadNodes();
  }

  protected async loadNodes(): Promise<void> {
    this.isLoading.set(true);
    this.error.set(null);
    try {
      const nodes = await firstValueFrom(this.resultsApi.getNodeIndex());
      this.nodes.set(nodes);
    } catch (err) {
      console.error('[ResultsOverview] Failed to load node index:', err);
    } finally {
      this.isLoading.set(false);
    }
  }

  protected goToNode(node: NodeResultSummary): void {
    void this.router.navigate(['/results', node.node_id]);
  }

  protected formatTimestamp(ts: number | null): string {
    if (ts === null) return 'No results yet';
    const date = new Date(ts * 1000);
    const diff = (Date.now() - date.getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
  }

  protected formatNodeType(nodeType: string): string {
    return nodeType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  protected nodeTypeIcon(nodeType: string): string {
    const iconMap: Record<string, string> = {
      result_storage: 'save',
      volume_calculation: 'view_in_ar',
      vehicle_profiler: 'directions_car',
      surface_inspection: 'grid_on',
    };
    return iconMap[nodeType] ?? 'analytics';
  }
}
