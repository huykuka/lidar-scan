// @ts-nocheck — suppress strict template type checks in tests
import {TestBed} from '@angular/core/testing';
import {MetadataTableComponent} from './metadata-table.component';
import {CUSTOM_ELEMENTS_SCHEMA} from '@angular/core';

/**
 * Unit tests for MetadataTableComponent (dumb/presentational).
 *
 * TDD: written before / alongside implementation to verify contract:
 *   - Empty state when metadata is null
 *   - Renders all scalar fields
 *   - Renders nested objects as JSON inside <pre>
 *   - Renders null values as em dash
 *   - Correct type labels
 */
describe('MetadataTableComponent', () => {
  beforeEach(async () => {
    // Polyfill Synergy web-component animations API
    if (!(Element.prototype as any).getAnimations) {
      (Element.prototype as any).getAnimations = () => [];
    }

    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [MetadataTableComponent],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Empty state
  // ──────────────────────────────────────────────────────────────────────────

  it('renders empty state when metadata is null', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', null);
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.textContent).toContain('Waiting for data...');
    expect(compiled.querySelector('table')).toBeNull();
  });

  it('renders empty state when metadata is undefined (not passed)', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    // metadata defaults to null — don't set it
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.textContent).toContain('Waiting for data...');
  });

  it('renders "no metadata fields" state for empty object', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {});
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.textContent).toContain('No metadata fields received');
    expect(compiled.querySelector('table')).toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Table rendering — scalar fields
  // ──────────────────────────────────────────────────────────────────────────

  it('renders all fields from metadata object', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {
      point_count: 45000,
      sensor_name: 'lidar_front',
    });
    fixture.detectChanges();

    const compiled: HTMLElement = fixture.nativeElement;
    expect(compiled.textContent).toContain('point_count');
    expect(compiled.textContent).toContain('45000');
    expect(compiled.textContent).toContain('sensor_name');
    expect(compiled.textContent).toContain('lidar_front');
    expect(compiled.querySelector('table')).not.toBeNull();
  });

  it('renders number values correctly', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {intensity_avg: 0.72});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('0.72');
  });

  it('renders boolean values correctly', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {active: true});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('true');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Complex values — objects and arrays
  // ──────────────────────────────────────────────────────────────────────────

  it('renders nested objects as formatted JSON inside <pre>', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {pose: {x: 1, y: 2}});
    fixture.detectChanges();

    const pre = fixture.nativeElement.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toContain('"x": 1');
  });

  it('renders arrays as formatted JSON inside <pre>', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {indices: [1, 2, 3]});
    fixture.detectChanges();

    const pre = fixture.nativeElement.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toContain('1');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Null / undefined values
  // ──────────────────────────────────────────────────────────────────────────

  it('renders null value as em dash', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {missing_field: null});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('—');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Type column labels
  // ──────────────────────────────────────────────────────────────────────────

  it('shows "number" type label for numeric values', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel'](42)).toBe('number');
  });

  it('shows "string" type label for string values', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel']('hello')).toBe('string');
  });

  it('shows "boolean" type label for boolean values', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel'](true)).toBe('boolean');
  });

  it('shows "null" type label for null values', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel'](null)).toBe('null');
  });

  it('shows "array" type label for arrays', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel']([1, 2, 3])).toBe('array');
  });

  it('shows "object" type label for plain objects', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['typeLabel']({a: 1})).toBe('object');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // renderValue helper
  // ──────────────────────────────────────────────────────────────────────────

  it('renderValue returns em dash for null', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    expect(fixture.componentInstance['renderValue'](null)).toBe('—');
  });

  it('renderValue returns em dash for undefined', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    expect(fixture.componentInstance['renderValue'](undefined)).toBe('—');
  });

  it('renderValue returns string representation of primitives', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const comp = fixture.componentInstance;
    expect(comp['renderValue'](42)).toBe('42');
    expect(comp['renderValue'](true)).toBe('true');
    expect(comp['renderValue']('hello')).toBe('hello');
  });

  it('renderValue returns JSON for objects', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    const result = fixture.componentInstance['renderValue']({key: 'val'});
    expect(result).toContain('"key"');
    expect(result).toContain('"val"');
  });

  // ──────────────────────────────────────────────────────────────────────────
  // Reactivity — re-renders when metadata input changes
  // ──────────────────────────────────────────────────────────────────────────

  it('updates table when metadata input changes from null to data', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', null);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Waiting for data...');

    fixture.componentRef.setInput('metadata', {point_count: 1000});
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('table')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('point_count');
  });

  it('updates table when metadata fields change', () => {
    const fixture = TestBed.createComponent(MetadataTableComponent);
    fixture.componentRef.setInput('metadata', {field_a: 1});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('field_a');
    expect(fixture.nativeElement.textContent).not.toContain('field_b');

    fixture.componentRef.setInput('metadata', {field_b: 2});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toContain('field_a');
    expect(fixture.nativeElement.textContent).toContain('field_b');
  });
});
