import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { ResultsApiService, MOCK_NODE_INDEX } from '@core/services/api/results-api.service';
import { NavigationService } from '@core/services';
import { PcdFileEntry, ResultDetail } from '@core/models';
import { MetadataTableComponent } from '../shared/metadata-table/metadata-table.component';
import { PcdViewerComponent } from '../shared/pcd-viewer/pcd-viewer.component';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-result-detail',
  standalone: true,
  imports: [SynergyComponentsModule, RouterModule, MetadataTableComponent, PcdViewerComponent],
  templateUrl: './result-detail.component.html',
  styleUrl: './result-detail.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResultDetailComponent implements OnInit {
  protected nodeId = signal<string>('');
  protected resultId = signal<string>('');
  protected nodeName = signal<string>('');
  protected result = signal<ResultDetail | null>(null);
  protected isLoading = signal(false);
  protected notFound = signal(false);
  protected activeLabel = signal<string>('');

  /** Precomputed map from label → {url, color} to avoid method calls in template. */
  protected pcdFileMap = signal<Map<string, { url: string; color: string }>>(new Map());

  /** The currently active PcdFileEntry, derived from activeLabel. */
  protected activeTab = computed<PcdFileEntry | undefined>(() =>
    this.result()?.pcd_files.find((f) => f.label === this.activeLabel()),
  );

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

  ngOnInit(): void {
    const nodeId = this.route.snapshot.paramMap.get('nodeId') ?? '';
    const resultId = this.route.snapshot.paramMap.get('resultId') ?? '';
    this.nodeId.set(nodeId);
    this.resultId.set(resultId);
    this.loadDetail(nodeId, resultId);

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
      // Precompute url+color map so template never calls methods on each CD cycle
      const map = new Map<string, { url: string; color: string }>();
      for (const f of detail.pcd_files) {
        map.set(f.label, {
          url: this.resultsApi.getPcdUrl(`data/${f.path}`),
          color: f.color ?? '',
        });
      }
      this.pcdFileMap.set(map);
      if (detail.pcd_files.length > 0) {
        this.activeLabel.set(detail.pcd_files[0].label);
      }
    } catch (err: any) {
      if (err?.status === 404) {
        this.notFound.set(true);
      }
    } finally {
      this.isLoading.set(false);
    }
  }

  /** Called by syn-tab-group's syn-tab-show event when the user switches tabs. */
  protected onTabShow(event: Event): void {
    const detail = (event as CustomEvent<{ name: string }>).detail;
    this.activeLabel.set(detail.name);
  }

  protected downloadPcd(pcd: PcdFileEntry): void {
    const entry = this.pcdFileMap().get(pcd.label);
    if (!entry?.url) return;
    const a = document.createElement('a');
    a.href = entry.url;
    a.download = `${pcd.label}.pcd`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  protected formatTimestamp(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  protected statusVariant(
    status: string,
  ): 'success' | 'warning' | 'danger' | 'neutral' | 'primary' {
    const map: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
      success: 'success',
      warning: 'warning',
      error: 'danger',
    };
    return map[status] ?? 'neutral';
  }
}
