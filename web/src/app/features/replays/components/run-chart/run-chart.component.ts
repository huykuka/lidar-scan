import {ChangeDetectionStrategy, Component, computed, input} from '@angular/core';
import {SynChartComponent} from '@synergy-design-system/angular/components/chart';
import type {ECConfig} from '@synergy-design-system/components/components/chart/types.js';
import {cssVar} from '../../utils/chart-theme';
import {SeriesPoint} from '../../utils/run-series';

/** One value of one run over the frames, with its average as a reference line. */
@Component({
  selector: 'app-run-chart',
  imports: [SynChartComponent],
  template: `<syn-chart [config]="config()" [attr.aria-label]="'Value over frames: ' + label()" [class]="compact() ? 'block h-52' : 'block h-80'" />`,
  styles: [':host { display: block; }'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RunChartComponent {
  readonly points = input.required<SeriesPoint[]>();
  readonly label = input('value');
  readonly mean = input<number | null>(null);
  /** Small card variant: shorter, no zoom slider. */
  readonly compact = input(false);

  protected readonly config = computed((): ECConfig => {
    const color = cssVar('--syn-color-primary-600', '#2563eb');
    const mean = this.mean();
    const compact = this.compact();
    const values = this.points().map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    // A flat line would otherwise get an arbitrary axis; centre it with some headroom.
    const pad = lo === hi ? Math.max(Math.abs(lo) * 0.1, 1) : 0;
    return {
      color: [color],
      grid: {left: 64, right: 24, top: 16, bottom: compact ? 32 : 72},
      dataZoom: compact ? [{type: 'inside' as const}] : [{type: 'inside' as const}, {type: 'slider' as const, height: 18, bottom: 8}],
      tooltip: {trigger: 'axis' as const},
      xAxis: {type: 'value' as const, name: 'frame', nameLocation: 'middle' as const, nameGap: 22, min: 'dataMin', max: 'dataMax'},
      yAxis: {type: 'value' as const, scale: true, ...(pad ? {min: lo - pad, max: hi + pad} : {})},
      series: [
        {
          name: this.label(),
          type: 'line' as const,
          showSymbol: false,
          lineStyle: {width: 1.5, color},
          itemStyle: {color},
          data: this.points().map((p) => [p.frame, p.value]),
          markLine:
            mean === null
              ? undefined
              : {
                  silent: true,
                  symbol: 'none',
                  lineStyle: {type: 'dashed' as const, color: cssVar('--syn-color-neutral-500', '#6b7280')},
                  label: {formatter: 'average'},
                  data: [{yAxis: mean}],
                },
        },
      ],
    };
  });
}
