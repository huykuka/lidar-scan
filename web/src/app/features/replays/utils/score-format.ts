import {RunScores, ScoreStatus, TargetScore} from '@core/models';

export type BadgeVariant = 'success' | 'danger' | 'neutral' | 'warning';

export function scoreVariant(status: ScoreStatus | null | undefined): BadgeVariant {
  switch (status) {
    case 'pass':
      return 'success';
    case 'fail':
      return 'danger';
    case 'missing':
      return 'warning';
    default:
      return 'neutral';
  }
}

export function scoreLabel(status: ScoreStatus | null | undefined): string {
  switch (status) {
    case 'pass':
      return 'Pass';
    case 'fail':
      return 'Fail';
    case 'missing':
      return 'No data';
    case 'info':
      return 'Measured';
    default:
      return '';
  }
}

/** Compact number for tables (4 significant digits, no trailing noise). */
export function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toPrecision(digits)));
}

export function signed(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return '—';
  const text = formatNumber(value, digits);
  return value > 0 ? `+${text}` : text;
}

/** "+0.05 (0.83%)" for a target score; "no data" when the run did not produce the metric. */
export function describeError(score: TargetScore): string {
  if (score.error === null) return 'no data';
  const pct = score.pct_error === null ? '' : ` (${signed(score.pct_error, 3)}%)`;
  return `${signed(score.error)}${pct}`;
}

/** The target worth showing in a one-line cell: the worst failing one, else the first. */
export function headlineTarget(scores: RunScores | null | undefined): TargetScore | null {
  if (!scores || scores.targets.length === 0) return null;
  return scores.targets.find((t) => t.status === 'fail') ?? scores.targets.find((t) => t.status === 'missing') ?? scores.targets[0];
}
