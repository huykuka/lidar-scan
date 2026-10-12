import {AbstractControl, ValidationErrors} from '@angular/forms';
import {NodeDefinition, PropertySchema} from '@core/models/node.model';

/** Values are parsed as JSON when possible (numbers, booleans, lists), else kept as text. */
export function parseOverrideValue(raw: string): unknown {
  const text = raw.trim();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Parameters that make no sense to override in an offline replay. */
const EXCLUDED_PROPERTY_TYPES = new Set(['pose']);
const EXCLUDED_PROPERTY_NAMES = new Set(['throttle_ms']); // throttling is disabled during replay

/** Parameters of a node type that can be overridden for a replay run. */
export function overridableProperties(def: NodeDefinition | undefined): PropertySchema[] {
  return (def?.properties ?? []).filter(
    (p) => !p.hidden && !EXCLUDED_PROPERTY_TYPES.has(p.type) && !EXCLUDED_PROPERTY_NAMES.has(p.name),
  );
}

/** Text shown in the value input for a given value (what the user would type). */
export function formatOverrideValue(value: unknown): string {
  if (value === undefined || value === null) return '';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

/**
 * Convert the raw text from the value input to the typed value sent to the backend,
 * according to the parameter schema. Returns ``undefined`` when the text is not valid.
 */
export function resolveOverrideValue(prop: PropertySchema | undefined, raw: string): unknown {
  const text = (raw ?? '').trim();
  if (!prop) return parseOverrideValue(text);
  switch (prop.type) {
    case 'boolean':
      return text === 'true' ? true : text === 'false' ? false : undefined;
    case 'number': {
      const n = Number(text);
      return text !== '' && Number.isFinite(n) ? n : undefined;
    }
    case 'select': {
      const option = prop.options?.find((o) => String(o.value) === text);
      return option ? option.value : text === '' ? undefined : parseOverrideValue(text);
    }
    default:
      return text === '' ? undefined : parseOverrideValue(text);
  }
}

/** An override row is either completely empty (ignored) or needs node, parameter and value. */
export function overrideRowValidator(row: AbstractControl): ValidationErrors | null {
  const {nodeId, key, value} = row.value as {nodeId: string; key: string; value: string};
  const touched = !!nodeId || !!key?.trim() || !!value?.trim();
  return touched && (!nodeId || !key?.trim() || !value?.trim()) ? {incompleteOverride: true} : null;
}

