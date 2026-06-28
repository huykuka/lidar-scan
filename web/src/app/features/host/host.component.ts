import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  OnInit,
  signal,
  CUSTOM_ELEMENTS_SCHEMA,
} from '@angular/core';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { HostApiService, HostSnapshot, HostCpuInfo } from '@core/services/api/host-api.service';
import { NavigationService } from '@core/services';

const POLL_MS = 3000;
const MAX_POINTS = 60; // ~3 min of history at 3s interval

interface TimeSeriesPoint {
  time: string;
  values: number[];
}

function nowLabel(): string {
  return new Date().toLocaleTimeString();
}

@Component({
  selector: 'app-host',
  standalone: true,
  imports: [SynergyComponentsModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './host.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: flex; flex-direction: column; height: 100%; }
    .chart-wrap { width: 100%; height: 260px; display: block; }
    .chart-wrap syn-chart { width: 100%; height: 100%; }
    .progress-bar-bg {
      height: 8px; border-radius: 4px;
      background: var(--syn-color-neutral-200);
      overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%; border-radius: 4px;
      background: var(--syn-color-primary-600);
      transition: width 0.4s ease;
    }
  `,
})
export class HostComponent implements OnInit, OnDestroy {
  private api = inject(HostApiService);
  private navService = inject(NavigationService);
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  readonly snapshot = signal<HostSnapshot | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  // ── CPU time-series history ───────────────────────────────────────────────
  private cpuHistory = signal<TimeSeriesPoint[]>([]);
  private loadHistory = signal<TimeSeriesPoint[]>([]);

  readonly cpuChartConfig = computed(() => {
    const history = this.cpuHistory();
    if (!history.length) return null;

    const times = history.map(p => p.time);
    const snap = this.snapshot();
    const coreCount = snap?.cpu.percent_per_core.length ?? 0;
    const last = history.at(-1);

    // Build series: Total (thick, legend-visible) + each core (thin, legend-hidden)
    const series: any[] = [
      {
        name: 'Total',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.5 },
        data: history.map(p => p.values[0]),
      },
      ...Array.from({ length: coreCount }, (_, i) => ({
        name: `Core ${i + 1}`,
        type: 'line',
        smooth: true,
        symbol: 'none',
        legendHoverLink: false,
        lineStyle: { width: 1, opacity: 0.7 },
        data: history.map(p => p.values[i + 1] ?? 0),
      })),
    ];

    const totalVal = last?.values[0]?.toFixed(1) ?? '—';

    return {
      grid: { left: 48, right: 16, top: 12, bottom: 32 },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (params: any[]) =>
          params.map((p: any) => `${p.marker}${p.seriesName}: <b>${(p.value as number).toFixed(1)}%</b>`).join('<br>'),
      },
      legend: {
        bottom: 0,
        itemHeight: 8,
        itemWidth: 16,
        textStyle: { fontSize: 11 },
        // Only show "Total" in legend; cores visible via tooltip
        selected: Object.fromEntries([
          ['Total', true],
          ...Array.from({ length: coreCount }, (_, i) => [`Core ${i + 1}`, false]),
        ]),
        formatter: () => `Total:  ${totalVal}%`,
        data: ['Total'],
      },
      xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%', fontSize: 10 } },
      series,
    };
  });

  readonly loadChartConfig = computed(() => {
    const history = this.loadHistory();
    if (!history.length) return null;

    const times = history.map(p => p.time);
    const labels = ['1 min', '5 min', '15 min'];
    const last = history.at(-1);

    return {
      grid: { left: 48, right: 16, top: 12, bottom: 32 },
      tooltip: {
        trigger: 'axis',
        confine: true,
        formatter: (params: any[]) =>
          params.map((p: any) => `${p.marker}${p.seriesName}: <b>${(p.value as number).toFixed(2)}</b>`).join('<br>'),
      },
      legend: {
        bottom: 0,
        itemHeight: 8,
        itemWidth: 16,
        textStyle: { fontSize: 11 },
        formatter: (name: string) => {
          const idx = labels.indexOf(name);
          const val = last?.values[idx]?.toFixed(2) ?? '—';
          return `${name}: ${val}`;
        },
      },
      xAxis: { type: 'category', data: times, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
      series: labels.map((label, i) => ({
        name: label,
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: history.map(p => p.values[i] ?? 0),
      })),
    };
  });

  // ── CPU core usage bars ───────────────────────────────────────────────────
  readonly coreUsages = computed(() => {
    const s = this.snapshot();
    if (!s) return [];
    return [
      { label: 'Total', pct: s.cpu.percent_total },
      ...s.cpu.percent_per_core.map((pct, i) => ({ label: `Core ${i + 1}`, pct })),
    ];
  });

  // ── Memory progress bars ──────────────────────────────────────────────────
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

  // ── Disk bars ─────────────────────────────────────────────────────────────
  readonly partitions = computed(() => this.snapshot()?.disk.partitions ?? []);

  // ── Network ───────────────────────────────────────────────────────────────
  readonly interfaces = computed(() => this.snapshot()?.network.interfaces ?? []);

  // ── Host info ─────────────────────────────────────────────────────────────
  readonly hostInfo = computed(() => this.snapshot()?.host ?? null);
  readonly processInfo = computed(() => this.snapshot()?.process ?? null);

  formatUptime(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────
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
      this.appendCpuHistory(snap.cpu);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Failed to load host data');
    } finally {
      this.loading.set(false);
    }
  }

  private appendCpuHistory(cpu: HostCpuInfo): void {
    const t = nowLabel();

    this.cpuHistory.update(h => {
      const next = [...h, { time: t, values: [cpu.percent_total, ...cpu.percent_per_core] }];
      return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
    });

    this.loadHistory.update(h => {
      const next = [...h, { time: t, values: cpu.load_avg_1_5_15 }];
      return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
    });
  }
}
