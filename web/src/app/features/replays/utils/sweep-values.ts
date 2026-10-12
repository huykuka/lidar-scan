import {PropertySchema} from '@core/models/node.model';

/** Backend limit for one sweep (including the baseline run). */
export const MAX_SWEEP_RUNS = 30;

/** Parameters that can be swept: ones with a finite, enumerable or numeric domain. */
export function isSweepable(prop: PropertySchema): boolean {
  return !prop.hidden && prop.name !== 'throttle_ms' && ['number', 'boolean', 'select'].includes(prop.type);
}

/** Round away floating-point noise from repeated addition (0.1 + 0.2 -> 0.3). */
function tidy(value: number, step: number): number {
  const decimals = Math.min(10, Math.max(0, Math.ceil(-Math.log10(Math.abs(step) || 1)) + 2));
  return Number(value.toFixed(decimals));
}

export type RangeResult = {values: number[]; error: string | null};

/**
 * Inclusive range ``start..end`` in steps of ``step``. Returns an error message instead of
 * values when the inputs would produce nothing useful or too many runs.
 */
export function rangeValues(start: number, end: number, step: number, maxValues = MAX_SWEEP_RUNS): RangeResult {
  if (![start, end, step].every(Number.isFinite)) return {values: [], error: 'Enter start, end and step'};
  if (step <= 0) return {values: [], error: 'Step must be greater than 0'};
  if (end < start) return {values: [], error: 'End must not be below start'};
  const count = Math.floor((end - start) / step + 1e-9) + 1;
  if (count > maxValues) return {values: [], error: `That makes ${count} runs; the limit is ${maxValues}`};
  return {values: Array.from({length: count}, (_, i) => tidy(start + i * step, step)), error: null};
}

/** Parse "0.3, 0.5; 1" into numbers. Invalid entries are reported, not dropped silently. */
export function parseNumberList(text: string): {values: number[]; error: string | null} {
  const parts = text.split(/[\s,;]+/).filter(Boolean);
  if (parts.length === 0) return {values: [], error: 'Enter at least one value'};
  const values = parts.map(Number);
  const bad = parts.find((_, i) => !Number.isFinite(values[i]));
  if (bad !== undefined) return {values: [], error: `"${bad}" is not a number`};
  return {values: [...new Set(values)], error: null};
}

/** Human summary of sweep values for tables: "5 values: 0.3 … 1.5". */
export function describeValues(values: unknown[]): string {
  if (values.length === 0) return 'no values';
  const text = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));
  if (values.length <= 4) return values.map(text).join(', ');
  return `${values.length} values: ${text(values[0])} … ${text(values[values.length - 1])}`;
}

/**
 * A sensible starting range around the parameter's current value: five values from half to
 * one-and-a-half times the current value, clamped to the parameter's min/max when known.
 */
export function defaultRange(
  current: unknown,
  prop?: Pick<PropertySchema, 'min' | 'max'>,
): {start: number; end: number; step: number} {
  const c = typeof current === 'number' ? current : Number(current);
  let start = Number.isFinite(c) && c !== 0 ? c * 0.5 : 0;
  let end = Number.isFinite(c) && c !== 0 ? c * 1.5 : 1;
  if (prop?.min !== undefined) start = Math.max(start, prop.min);
  if (prop?.max !== undefined) end = Math.min(end, prop.max);
  if (end <= start) end = start + 1;
  const round = (v: number) => Number(v.toPrecision(3));
  start = round(start);
  end = round(end);
  return {start, end, step: round((end - start) / 4)};
}

/** Number of runs a sweep will create: the values plus the baseline when it is not among them. */
export function plannedRuns(values: unknown[], current: unknown, includeCurrent: boolean): number {
  const same = (a: unknown, b: unknown) => Number(a) === Number(b) || a === b;
  const baseline = includeCurrent && current !== undefined && current !== null && !values.some((v) => same(v, current));
  return values.length + (baseline ? 1 : 0);
}
