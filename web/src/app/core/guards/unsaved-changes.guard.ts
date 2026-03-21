import {inject} from '@angular/core';
import {CanDeactivateFn} from '@angular/router';
import {CanvasEditStoreService} from '@features/settings/services/canvas-edit-store.service';
import {DialogService} from '@core/services/dialog.service';

export const unsavedChangesGuard: CanDeactivateFn<unknown> = async () => {
  const store = inject(CanvasEditStoreService);
  if (!store.isDirty()) return true;
  const dialog = inject(DialogService);
  return dialog.confirm({
    title: 'Unsaved Changes',
    message: 'You have unsaved changes on the canvas. Leaving will discard them.',
    confirmLabel: 'Leave & Discard',
    cancelLabel: 'Stay',
    variant: 'danger',
  });
};
