import {FormControl, FormGroup} from '@angular/forms';
import {PropertySchema} from '@core/models/node.model';
import {
  formatOverrideValue,
  overridableProperties,
  overrideRowValidator,
  parseOverrideValue,
  resolveOverrideValue,
} from './replay-form.component';

describe('parseOverrideValue', () => {
  it('parses numbers, booleans and lists as JSON', () => {
    expect(parseOverrideValue('1.5')).toBe(1.5);
    expect(parseOverrideValue(' true ')).toBe(true);
    expect(parseOverrideValue('[1, 2]')).toEqual([1, 2]);
  });

  it('keeps non-JSON text as a string', () => {
    expect(parseOverrideValue('radius_outlier')).toBe('radius_outlier');
  });
});

describe('overrideRowValidator', () => {
  const row = (nodeId: string, key: string, value: string) =>
    new FormGroup(
      {nodeId: new FormControl(nodeId), key: new FormControl(key), value: new FormControl(value)},
      {validators: overrideRowValidator},
    );

  it('accepts a completely empty row (ignored on submit)', () => {
    expect(row('', '', '').valid).toBe(true);
  });

  it('accepts a complete row', () => {
    expect(row('n1', 'radius', '1.5').valid).toBe(true);
  });

  it('rejects a row with a value but no node or parameter', () => {
    expect(row('', '', '1.5').errors).toEqual({incompleteOverride: true});
    expect(row('n1', ' ', '1.5').errors).toEqual({incompleteOverride: true});
  });

  it('rejects a row that has a parameter but no value', () => {
    expect(row('n1', 'radius', '').errors).toEqual({incompleteOverride: true});
  });
});

const prop = (p: Partial<PropertySchema>): PropertySchema =>
  ({name: 'p', label: 'P', type: 'string', ...p}) as PropertySchema;

describe('overridableProperties', () => {
  it('hides hidden, pose and throttle parameters', () => {
    const def: any = {
      properties: [
        prop({name: 'radius', type: 'number'}),
        prop({name: 'throttle_ms', type: 'number'}),
        prop({name: 'pose', type: 'pose'}),
        prop({name: 'secret', hidden: true}),
      ],
    };
    expect(overridableProperties(def).map((p) => p.name)).toEqual(['radius']);
  });

  it('returns an empty list for an unknown node type', () => {
    expect(overridableProperties(undefined)).toEqual([]);
  });
});

describe('resolveOverrideValue', () => {
  it('converts numbers and rejects invalid ones', () => {
    expect(resolveOverrideValue(prop({type: 'number'}), '1.5')).toBe(1.5);
    expect(resolveOverrideValue(prop({type: 'number'}), 'abc')).toBeUndefined();
    expect(resolveOverrideValue(prop({type: 'number'}), '')).toBeUndefined();
  });

  it('converts booleans', () => {
    expect(resolveOverrideValue(prop({type: 'boolean'}), 'true')).toBe(true);
    expect(resolveOverrideValue(prop({type: 'boolean'}), 'false')).toBe(false);
    expect(resolveOverrideValue(prop({type: 'boolean'}), 'maybe')).toBeUndefined();
  });

  it('keeps the original option value for select parameters', () => {
    const p = prop({type: 'select', options: [{label: 'A', value: 1}, {label: 'B', value: 'b'}]});
    expect(resolveOverrideValue(p, '1')).toBe(1);
    expect(resolveOverrideValue(p, 'b')).toBe('b');
  });

  it('parses vectors as JSON', () => {
    expect(resolveOverrideValue(prop({type: 'vec3'}), '[-10, 0, 2]')).toEqual([-10, 0, 2]);
  });
});

describe('formatOverrideValue', () => {
  it('formats saved values for the input', () => {
    expect(formatOverrideValue(0.7)).toBe('0.7');
    expect(formatOverrideValue('50')).toBe('50');
    expect(formatOverrideValue(true)).toBe('true');
    expect(formatOverrideValue([1, 2])).toBe('[1,2]');
    expect(formatOverrideValue(undefined)).toBe('');
  });
});
