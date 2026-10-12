import {ChangeDetectionStrategy, Component, computed, input} from '@angular/core';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {RunScores} from '@core/models';
import {describeError, formatNumber, headlineTarget, scoreLabel, scoreVariant} from '../../utils/score-format';

/** One-line result of a run against the recording's ground truth. */
@Component({
  selector: 'app-replay-score',
  imports: [SynergyComponentsModule],
  templateUrl: './replay-score.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReplayScoreComponent {
  readonly scores = input<RunScores | null | undefined>(null);

  protected readonly headline = computed(() => headlineTarget(this.scores()));
  protected readonly variant = computed(() => scoreVariant(this.scores()?.overall));
  protected readonly label = computed(() => scoreLabel(this.scores()?.overall));
  protected readonly extra = computed(() => Math.max((this.scores()?.targets.length ?? 0) - 1, 0));
  protected readonly error = computed(() => {
    const t = this.headline();
    return t ? describeError(t) : '';
  });
  /** Full detail for the hover text (every target). */
  protected readonly tooltip = computed(() =>
    (this.scores()?.targets ?? [])
      .map((t) => {
        const tol = t.tolerance === null ? '' : ` ±${formatNumber(t.tolerance)}`;
        return `${t.label}: ${formatNumber(t.value)} (expected ${formatNumber(t.expected)}${tol}) · ${describeError(t)}`;
      })
      .join('\n'),
  );
}
