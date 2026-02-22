import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { WorkspaceViewControlsComponent } from './workspace-view-controls.component';
import { WorkspaceStoreService } from '../../../../core/services/stores/workspace-store.service';
import { WorkspaceViewControlsButtonComponent } from './workspace-view-controls-button.component';

describe('WorkspaceViewControlsComponent', () => {
  let store: WorkspaceStoreService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceViewControlsComponent],
    }).compileComponents();
    store = TestBed.inject(WorkspaceStoreService);
  });

  it('toggles HUD via first control button click', () => {
    store.set('showHud', true);

    const fixture = TestBed.createComponent(WorkspaceViewControlsComponent);
    fixture.detectChanges();

    const buttons = fixture.debugElement.queryAll(By.directive(WorkspaceViewControlsButtonComponent));
    expect(buttons.length).toBeGreaterThan(0);

    const hudBtn = buttons[0].componentInstance as WorkspaceViewControlsButtonComponent;
    hudBtn.clicked.emit();
    fixture.detectChanges();

    expect(store.showHud()).toBe(false);
  });
});
