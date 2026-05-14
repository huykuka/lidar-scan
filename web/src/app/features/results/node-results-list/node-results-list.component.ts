import {Component, effect, inject, OnInit, signal} from '@angular/core';
import {ActivatedRoute, Router, RouterModule} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ResultsApiService, MOCK_RESULTS_BY_NODE, MOCK_NODE_INDEX} from '@core/services/api/results-api.service';
import {NavigationService} from '@core/services';
import {NodeResultSummary, ResultSummary} from '@core/models';
import {firstValueFrom} from 'rxjs';

@Component({
  selector: 'app-node-results-list',
  standalone: true,
  imports: [SynergyComponentsModule, RouterModule],
  templateUrl: './node-results-list.component.html',
  styleUrl: './node-results-list.component.css',
})
export class NodeResultsListComponent implements OnInit {
  protected nodeId = signal<string>('');
  protected nodeName = signal<string>('');
  protected results = signal<ResultSummary[]>([]);
  protected isLoading = signal(false);
  protected error = signal<string | null>(null);

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private resultsApi = inject(ResultsApiService);
  private navService = inject(NavigationService);

  constructor() {
    effect(() => {
      const id = this.nodeId();
      if (id) {
        void this.loadResults(id);
      }
    });
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('nodeId') ?? '';
    this.nodeId.set(id);
    const node = MOCK_NODE_INDEX.find((n) => n.node_id === id);
    const name = node?.node_name ?? 'Unnamed';
    this.nodeName.set(name);
    this.navService.setPageConfig({
      title: 'Results',
      subtitle: `${name} — run history`,
    });
  }

  protected async loadResults(nodeId: string): Promise<void> {
    this.isLoading.set(true);
    this.error.set(null);
    try {
      const results = await firstValueFrom(this.resultsApi.getResultsByNode(nodeId));
      this.results.set(results);
    } catch {
      // Fallback to mock
      this.results.set(MOCK_RESULTS_BY_NODE[nodeId] ?? []);
    } finally {
      this.isLoading.set(false);
    }
  }

  protected goToResult(result: ResultSummary): void {
    void this.router.navigate(['/results', result.node_id, result.result_id]);
  }

  protected formatTimestamp(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  protected statusVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' | 'primary' {
    const map: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
      success: 'success',
      warning: 'warning',
      error: 'danger',
    };
    return map[status] ?? 'neutral';
  }

  protected metaSummaryDisplay(metadata: Record<string, unknown>): string {
    return Object.entries(metadata)
      .slice(0, 3)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' · ');
  }

  protected get nodeResultSummary(): NodeResultSummary | undefined {
    return MOCK_NODE_INDEX.find((n) => n.node_id === this.nodeId());
  }
}
