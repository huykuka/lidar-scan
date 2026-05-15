import {ComponentFixture, TestBed} from '@angular/core/testing';
import {MetadataTableComponent} from './metadata-table.component';

describe('MetadataTableComponent', () => {
  let component: MetadataTableComponent;
  let fixture: ComponentFixture<MetadataTableComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MetadataTableComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MetadataTableComponent);
    component = fixture.componentInstance;
  });

  it('should render flat key-value metadata', () => {
    fixture.componentRef.setInput('metadata', {volume_m3: 12.4, icp_valid: true});
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('volume_m3');
    // Numbers are now rendered to 3 decimal places
    expect(fixture.nativeElement.textContent).toContain('12.400');
  });

  describe('number rendering (3 decimal places)', () => {
    it('should render a float to 3 decimal places', () => {
      fixture.componentRef.setInput('metadata', {pi: 3.14159});
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('3.142');
    });

    it('should render an integer to 3 decimal places', () => {
      fixture.componentRef.setInput('metadata', {count: 42});
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('42.000');
    });

    it('should render a float with fewer than 3 decimal digits padded', () => {
      fixture.componentRef.setInput('metadata', {val: 1.5});
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('1.500');
    });

    it('should NOT alter string values', () => {
      fixture.componentRef.setInput('metadata', {label: 'hello'});
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('hello');
    });

    it('should NOT alter boolean values', () => {
      fixture.componentRef.setInput('metadata', {flag: true});
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('true');
      expect(fixture.nativeElement.textContent).not.toContain('1.000');
    });
  });

  it('should render "No metadata available" for empty metadata', () => {
    fixture.componentRef.setInput('metadata', {});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('No metadata available');
  });

  it('should render complex values with Expand button', () => {
    fixture.componentRef.setInput('metadata', {nested: {a: 1, b: 2}});
    fixture.detectChanges();

    const expandBtn = fixture.nativeElement.querySelector('button');
    expect(expandBtn).toBeTruthy();
    expect(expandBtn.textContent).toContain('Expand');
  });

  it('should toggle collapse/expand for nested values', () => {
    fixture.componentRef.setInput('metadata', {nested: {a: 1}});
    fixture.detectChanges();

    const expandBtn = fixture.nativeElement.querySelector('button');
    expandBtn.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('pre')).toBeTruthy();
    expect(expandBtn.textContent).toContain('Collapse');

    expandBtn.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('pre')).toBeFalsy();
  });

  it('should render boolean values as strings', () => {
    fixture.componentRef.setInput('metadata', {icp_valid: false});
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('false');
  });
});
