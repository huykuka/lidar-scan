import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';
import {SynChartComponent} from '@synergy-design-system/angular/components/chart';
import {ChartPoint} from '../../utils/sweep-chart-geometry';
import type {ECConfig} from '@synergy-design-system/components/components/chart/types.js';
import {cssVar, SynChartElement, withChartInstance} from '../../utils/chart-theme';

/** Metric (mean ± std across frames) against the swept parameter, one dot per run. */
@Component({
  selector: 'app-sweep-chart',
  imports: [SynChartComponent],
  template: `<syn-chart #chart [config]="config()" [attr.aria-label]="'Sweep: ' + yLabel() + ' against ' + xLabel()" class="block h-72" />`,
  styles: [':host { display: block; }'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SweepChartComponent {
  readonly points = input.required<ChartPoint[]>();
  readonly expected = input<number | null>(null);
  readonly tolerance = input<number | null>(null);
  readonly selectedRunId = input<string | null>(null);
  readonly bestRunId = input<string | null>(null);
  readonly xLabel = input('');
  readonly yLabel = input('');

  readonly pointClick = output<string>();

  private readonly chart = viewChild.required('chart', {read: ElementRef<SynChartElement>});

  /** Points in plotting order: numeric parameters ascending, anything else as given. */
  private readonly ordered = computed(() => {
    const pts = this.points();
    return pts.length > 0 && pts.every((p) => typeof p.x === 'number')
      ? [...pts].sort((a, b) => (a.x as number) - (b.x as number))
      : pts;
  });

  protected readonly config = computed((): ECConfig => {
    const pts = this.ordered();
    const numericX = pts.length > 0 && pts.every((p) => typeof p.x === 'number');
    const primary = cssVar('--syn-color-primary-600', '#2563eb');
    const success = cssVar('--syn-color-success-600', '#16a34a');
    const neutral = cssVar('--syn-color-neutral-500', '#6b7280');
    const text = cssVar('--syn-color-neutral-900', '#111827');
    const xy = (p: ChartPoint, y: number | null) => (numericX ? [p.x as number, y] : y);

    const expected = this.expected();
    const tolerance = this.tolerance();
    const hasStd = pts.some((p) => p.std);

    const std = (name: string, sign: 1 | -1) => ({
      name,
      type: 'line' as const,
      silent: true,
      showSymbol: false,
      lineStyle: {width: 1, type: 'dashed' as const, color: neutral},
      itemStyle: {color: neutral},
      data: pts.map((p) => xy(p, p.y === null || !p.std ? null : p.y + sign * p.std)),
    });

    return {
      color: [primary],
      grid: {left: 56, right: 24, top: 24, bottom: 40},
      tooltip: {trigger: 'item' as const},
      xAxis: {
        type: numericX ? ('value' as const) : ('category' as const),
        name: this.xLabel(),
        nameLocation: 'middle' as const,
        nameGap: 26,
        ...(numericX ? {scale: true} : {data: pts.map((p) => String(p.x))}),
      },
      yAxis: {type: 'value' as const, scale: true, name: this.yLabel()},
      series: [
        {
          name: this.yLabel() || 'value',
          type: 'line' as const,
          showSymbol: true,
          symbol: 'circle',
          symbolSize: 11,
          lineStyle: {width: 1.5, color: primary},
          data: pts.map((p) => ({
            value: xy(p, p.y),
            itemStyle: {
              color: p.runId === this.bestRunId() ? success : primary,
              borderColor: p.runId === this.selectedRunId() ? text : '#fff',
              borderWidth: p.runId === this.selectedRunId() ? 3 : 2,
            },
          })),
          ...(expected !== null
            ? {
                markLine: {
                  silent: true,
                  symbol: 'none',
                  lineStyle: {color: success, type: 'dashed' as const},
                  label: {formatter: 'ground truth', position: 'insideEndTop' as const},
                  data: [{yAxis: expected}],
                },
                ...(tolerance
                  ? {
                      markArea: {
                        silent: true,
                        itemStyle: {color: success, opacity: 0.12},
                        data: [[{yAxis: expected - tolerance}, {yAxis: expected + tolerance}] as [{yAxis: number}, {yAxis: number}]],
                      },
                    }
                  : {}),
              }
            : {}),
        },
        ...(hasStd ? [std('mean + std', 1), std('mean − std', -1)] : []),
      ],
    };
  });

  constructor() {
    afterNextRender(() =>
      withChartInstance(this.chart().nativeElement, (chart) => {
        chart.on('click', (params) => {
          if (params.seriesIndex !== 0) return;
          const point = this.ordered()[params.dataIndex];
          if (point) this.pointClick.emit(point.runId);
        });
      }),
    );
  }
}
