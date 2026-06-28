import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { HostApiService, HostSnapshot } from '@core/services/api/host-api.service';
import { NavigationService } from '@core/services';

const POLL_MS = 3000;

@Component({
  selector: 'app-host',
  standalone: true,
  imports: [SynergyComponentsModule],
  templateUrl: './host.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; height: 100%; }
  `,
})
export class HostComponent implements OnInit, OnDestroy {
  private api = inject(HostApiService);
  private navService = inject(NavigationService);
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  readonly snapshot = signal<HostSnapshot | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  // ── CPU core usage bars ───────────────────────────────────────────────────
  readonly coreUsages = computed(() => {
    const s = this.snapshot();
    if (!s) return [];
    return [
      { label: 'Total', pct: s.cpu.percent_total },
      ...s.cpu.percent_per_core.map((pct, i) => ({ label: `Core ${i + 1}`, pct })),
    ];
  });

  // ── Memory ────────────────────────────────────────────────────────────────
  readonly ramPercent  = computed(() => this.snapshot()?.memory.ram.percent ?? 0);
  readonly swapPercent = computed(() => this.snapshot()?.memory.swap?.percent ?? 0);
  readonly swap        = computed(() => this.snapshot()?.memory.swap ?? null);

  readonly ramLabel = computed(() => {
    const m = this.snapshot()?.memory.ram;
    if (!m) return '—';
    return `${m.used_mb?.toFixed(0) ?? '?'} / ${m.total_mb?.toFixed(0) ?? '?'} MB`;
  });
  readonly swapLabel = computed(() => {
    const s = this.snapshot()?.memory.swap;
    if (!s) return '—';
    return `${s.used_mb?.toFixed(0) ?? '?'} / ${s.total_mb?.toFixed(0) ?? '?'} MB`;
  });

  // ── Disk / Network / Host ─────────────────────────────────────────────────
  readonly partitions  = computed(() => this.snapshot()?.disk.partitions ?? []);
  readonly interfaces  = computed(() => this.snapshot()?.network.interfaces ?? []);
  readonly hostInfo    = computed(() => this.snapshot()?.host ?? null);
  readonly processInfo = computed(() => this.snapshot()?.process ?? null);

  readonly cpuMeta = computed(() => {
    const s = this.snapshot();
    if (!s) return null;
    return {
      logical: s.cpu.count_logical,
      physical: s.cpu.count_physical,
      freq: s.cpu.freq_mhz.current,
      load: s.cpu.load_avg_1_5_15,
    };
  });

  formatUptime(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  pctVariant(pct: number): 'primary' | 'warning' | 'danger' {
    if (pct >= 90) return 'danger';
    if (pct >= 70) return 'warning';
    return 'primary';
  }

  pctColor(pct: number): string {
    if (pct >= 90) return 'var(--syn-color-error-600)';
    if (pct >= 70) return 'var(--syn-color-warning-600)';
    return 'var(--syn-color-primary-600)';
  }

  loadVariant(load: number, cores: number): 'success' | 'neutral' | 'warning' | 'danger' {
    const ratio = cores > 0 ? load / cores : load;
    if (ratio >= 1.5) return 'danger';
    if (ratio >= 0.8) return 'warning';
    if (ratio >= 0.1) return 'neutral';
    return 'success';
  }

  async ngOnInit(): Promise<void> {
    this.navService.setPageConfig({
      title: 'Resource Monitor',
      subtitle: 'Host system metrics — CPU, memory, disk and network',
    });
    await this.poll();
    this.pollTimer = setInterval(() => this.poll(), POLL_MS);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
  }

  private async poll(): Promise<void> {
    try {
      const snap = await this.api.getSnapshot();
      this.snapshot.set(snap);
      this.error.set(null);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Failed to load host data');
    } finally {
      this.loading.set(false);
    }
  }
}
