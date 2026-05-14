import {Component, computed, effect, inject, OnInit, signal} from '@angular/core';
import {ActivatedRoute, RouterModule} from '@angular/router';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {ResultsApiService, MOCK_RESULT_DETAIL, MOCK_NODE_INDEX} from '@core/services/api/results-api.service';
import {NavigationService} from '@core/services';
import {PcdFileEntry, ResultDetail} from '@core/models';
import {MetadataTableComponent} from '../shared/metadata-table/metadata-table.component';
import {PcdViewerComponent} from '../shared/pcd-viewer/pcd-viewer.component';
import {firstValueFrom} from 'rxjs';

@Component({
  selector: 'app-result-detail',
  standalone: true,
  imports: [SynergyComponentsModule, RouterModule, MetadataTableComponent, PcdViewerComponent],
  templateUrl: './result-detail.component.html',
  styleUrl: './result-detail.component.css',
})
export class ResultDetailComponent implements OnInit {
  protected nodeId = signal<string>('');
  protected resultId = signal<string>('');
  protected nodeName = signal<string>('');
  protected result = signal<ResultDetail | null>(null);
  protected isLoading = signal(false);
  protected notFound = signal(false);
  protected activeLabel = signal<string>('');

  /** Human-friendly breadcrumb label: "<Node Name> — <timestamp>" */
  protected resultBreadcrumb = computed<string>(() => {
    const r = this.result();
    const name = this.nodeName();
    if (!r) return name;
    const ts = this.formatTimestamp(r.timestamp);
    return `${name} — ${ts}`;
  });

  private route = inject(ActivatedRoute);
  private resultsApi = inject(ResultsApiService);
  private navService = inject(NavigationService);

  constructor() {
    effect(() => {
      const nodeId = this.nodeId();
      const resultId = this.resultId();
      if (nodeId && resultId) {
        void this.loadDetail(nodeId, resultId);
      }
    });
  }

  ngOnInit(): void {
    const nodeId = this.route.snapshot.paramMap.get('nodeId') ?? '';
    const resultId = this.route.snapshot.paramMap.get('resultId') ?? '';
    this.nodeId.set(nodeId);
    this.resultId.set(resultId);

    const node = MOCK_NODE_INDEX.find((n) => n.node_id === nodeId);
    this.nodeName.set(node?.node_name ?? 'Unnamed');

    this.navService.setPageConfig({
      title: 'Result Detail',
      subtitle: `${node?.node_name ?? 'Unnamed'}`,
    });
  }

  protected async loadDetail(nodeId: string, resultId: string): Promise<void> {
    this.isLoading.set(true);
    this.notFound.set(false);
    try {
      const detail = await firstValueFrom(this.resultsApi.getResultDetail(nodeId, resultId));
      this.result.set(detail);
      if (detail.pcd_files.length > 0) {
        this.activeLabel.set(detail.pcd_files[0].label);
      }
    } catch (err: any) {
      if (err?.status === 404) {
        this.notFound.set(true);
      } else {
        // Fallback to mock
        const mock = MOCK_RESULT_DETAIL[resultId];
        if (mock) {
          this.result.set(mock);
          if (mock.pcd_files.length > 0) {
            this.activeLabel.set(mock.pcd_files[0].label);
          }
        } else {
          this.notFound.set(true);
        }
      }
    } finally {
      this.isLoading.set(false);
    }
  }

  protected setActiveTab(pcdFile: PcdFileEntry): void {
    this.activeLabel.set(pcdFile.label);
  }

  protected get activePcdUrl(): string {
    const label = this.activeLabel();
    const entry = (this.result()?.pcd_files ?? []).find((f) => f.label === label);
    if (!entry) return '';
    // URL is always /data/${entry.path} — never uses download API or proxy.
    // entry.path is a relative path from the backend, e.g. 'results/<node_id>/<result_id>/<label>.pcd'
    return `/data/${entry.path}`;
  }

  /**
   * Returns the JSON-provided display color for the active PCD file.
   *
   * Sourced from `PcdFileEntry.color` in the Results API response.
   * When present, `PcdViewerComponent` will use this as a uniform `PointsMaterial.color`
   * and disable per-point vertex colors (`vertexColors = false`).
   * When absent, the viewer falls back to per-point RGB from the PCD binary.
   */
  protected get activePcdColor(): string {
    const label = this.activeLabel();
    const entry = (this.result()?.pcd_files ?? []).find((f) => f.label === label);
    return entry?.color ?? '';
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
}
