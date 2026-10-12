import {ChangeDetectionStrategy, Component, computed, input, output} from '@angular/core';
import {buildSweepChart, ChartPoint} from '../../utils/sweep-chart-geometry';

const WIDTH = 720;
const HEIGHT = 300;

/** Metric (mean ± std across frames) against the swept parameter, one dot per run. */
@Component({
  selector: 'app-sweep-chart',
  templateUrl: './sweep-chart.component.html',
  styleUrl: './sweep-chart.component.scss',
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

  protected readonly width = WIDTH;
  protected readonly height = HEIGHT;
  protected readonly chart = computed(() =>
    buildSweepChart(this.points(), {
      width: WIDTH,
      height: HEIGHT,
      expected: this.expected(),
      tolerance: this.tolerance(),
    }),
  );

  protected tooltip(label: string, value: number | null): string {
    return value === null ? `${label}: no data` : `${label}: ${Number(value.toPrecision(5))}`;
  }
}
