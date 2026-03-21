import {inject} from '@angular/core';
import {CanDeactivateFn} from '@angular/router';
import {DialogService} from '@core/services/dialog.service';

/** Any routed component that wants the unsaved-changes guard must implement this. */
export interface HasUnsavedChanges {
  hasUnsavedChanges(): boolean;
}

export const unsavedChangesGuard: CanDeactivateFn<HasUnsavedChanges> = async (component) => {
  if (!component.hasUnsavedChanges()) return true;
  const dialog = inject(DialogService);
  return dialog.confirm({
    title: 'Unsaved Changes',
    message: 'You have unsaved changes on the canvas. Leaving will discard them.',
    confirmLabel: 'Leave & Discard',
    cancelLabel: 'Stay',
    variant: 'danger',
  });
};
