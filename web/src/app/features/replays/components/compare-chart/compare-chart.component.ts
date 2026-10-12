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
import {ComparisonSeries} from '@core/models';
import type {ECConfig} from '@synergy-design-system/components/components/chart/types.js';
import {cssVar, SynChartElement, withChartInstance} from '../../utils/chart-theme';

/** One value over time, run A against run B. Clicking the plot reports the frame under the cursor. */
@Component({
  selector: 'app-compare-chart',
  imports: [SynChartComponent],
  template: `<syn-chart #chart [config]="config()" [attr.aria-label]="'A vs B for ' + series().key" class="block h-56 cursor-pointer" />`,
  styles: [':host { display: block; }'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CompareChartComponent {
  readonly series = input.required<ComparisonSeries>();
  /** Emits the frame number the user clicked. */
  readonly frameClick = output<number>();

  private readonly chart = viewChild.required('chart', {read: ElementRef<SynChartElement>});

  protected readonly config = computed((): ECConfig => {
    const s = this.series();
    const line = (name: string, color: string, pick: (p: ComparisonSeries['points'][number]) => number) => ({
      name,
      type: 'line' as const,
      showSymbol: false,
      lineStyle: {width: 1.5, color},
      itemStyle: {color},
      data: s.points.map((p) => [p.frame, pick(p)]),
    });
    return {
      color: [cssVar('--syn-color-neutral-600', '#6b7280'), cssVar('--syn-color-primary-600', '#2563eb')],
      grid: {left: 56, right: 16, top: 32, bottom: 32},
      legend: {data: ['A', 'B'], top: 0, right: 0},
      tooltip: {trigger: 'axis' as const},
      xAxis: {type: 'value' as const, name: 'frame', nameLocation: 'middle' as const, nameGap: 22, min: 'dataMin', max: 'dataMax'},
      yAxis: {type: 'value' as const, scale: true},
      series: [
        line('A', cssVar('--syn-color-neutral-600', '#6b7280'), (p) => p.a),
        line('B', cssVar('--syn-color-primary-600', '#2563eb'), (p) => p.b),
      ],
    };
  });

  constructor() {
    afterNextRender(() =>
      withChartInstance(this.chart().nativeElement, (chart) => {
        chart.getZr().on('click', (e) => {
          const point = [e.offsetX, e.offsetY];
          if (!chart.containPixel('grid', point)) return;
          const [frame] = chart.convertFromPixel({xAxisIndex: 0}, point) as number[];
          this.frameClick.emit(Math.round(frame));
        });
      }),
    );
  }
}
