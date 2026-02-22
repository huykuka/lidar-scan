import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { WorkspaceViewControlsButtonComponent } from './workspace-view-controls-button.component';

describe('WorkspaceViewControlsButtonComponent', () => {
  it('renders as icon-only button with title', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceViewControlsButtonComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceViewControlsButtonComponent);
    fixture.componentRef.setInput('label', 'Grid');
    fixture.componentRef.setInput('icon', 'grid_on');
    fixture.detectChanges();

    const btn = fixture.debugElement.query(By.css('syn-button'));
    expect(btn).toBeTruthy();
    expect(btn.attributes['title']).toBe('Grid');

    const icon = fixture.debugElement.query(By.css('syn-icon'));
    expect(icon).toBeTruthy();
    expect(icon.attributes['name']).toBe('grid_on');

    // Icon-only: do not render label text into the button.
    expect((fixture.nativeElement as HTMLElement).textContent || '').not.toContain('Grid');
  });
});
