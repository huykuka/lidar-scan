import { Component, inject, ChangeDetectionStrategy, computed } from '@angular/core';
import { SynDialogComponent, SynButtonComponent, SynIconComponent } from '@synergy-design-system/angular';
import { DialogService, DialogSeverity } from '@core/services/dialog.service';

/** Maps severity to Synergy color token overrides for syn-button */
const SEVERITY_STYLES: Record<DialogSeverity, string> = {
  danger:
    '--syn-color-primary-600: var(--syn-color-danger-600); --syn-color-primary-700: var(--syn-color-danger-700); --syn-color-primary-500: var(--syn-color-danger-500)',
  warning:
    '--syn-color-primary-600: var(--syn-color-warning-600); --syn-color-primary-700: var(--syn-color-warning-700); --syn-color-primary-500: var(--syn-color-warning-500)',
  success:
    '--syn-color-primary-600: var(--syn-color-success-600); --syn-color-primary-700: var(--syn-color-success-700); --syn-color-primary-500: var(--syn-color-success-500)',
  primary: '',
};

/**
 * DialogHostComponent
 *
 * Persistent global confirm dialog driven by DialogService signals.
 * Place once in app.component.html outside the router-outlet.
 *
 * Usage:
 *   this.dialogService.confirm({
 *     message: 'Are you sure?',
 *     confirmSeverity: 'danger',
 *     confirmIcon: 'delete',
 *     onConfirm: () => this.delete(id),
 *   });
 */
@Component({
  selector: 'app-dialog-host',
  imports: [SynDialogComponent, SynButtonComponent, SynIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <syn-dialog [label]="svc.title()" [open]="svc.isOpen()" (syn-request-close)="svc.cancel()">
      <p>{{ svc.message() }}</p>

      <div slot="footer" class="flex justify-end gap-2">
        <syn-button variant="outline" (click)="svc.cancel()"
          ><syn-icon slot="prefix" name="close" aria-hidden="true" />{{
            svc.cancelLabel()
          }}</syn-button
        >
        <syn-button variant="filled" [style]="confirmStyle()" (click)="svc.accept()"
          ><syn-icon slot="prefix" [name]="svc.confirmIcon()" aria-hidden="true" />{{
            svc.confirmLabel() || 'Delete'
          }}</syn-button
        >
      </div>
    </syn-dialog>
  `,
})
export class DialogHostComponent {
  protected readonly svc = inject(DialogService);

  protected readonly confirmStyle = computed(
    () => SEVERITY_STYLES[this.svc.confirmSeverity()] ?? '',
  );
}
