import {Injectable} from '@angular/core';

export interface ConfirmDialogOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'neutral';
}

@Injectable({
  providedIn: 'root',
})
export class DialogService {
  confirm(options: ConfirmDialogOptions | string): Promise<boolean> {
    const config: ConfirmDialogOptions =
      typeof options === 'string' ? {message: options} : options;

    const {
      title = 'Confirm',
      message,
      confirmLabel = 'Confirm',
      cancelLabel = 'Cancel',
      variant = 'danger',
    } = config;

    return new Promise<boolean>((resolve) => {
      const dialog = document.createElement('syn-dialog') as any;
      dialog.setAttribute('label', title);

      const confirmStyle =
        variant === 'danger'
          ? 'color: var(--syn-color-error-700); border-color: var(--syn-color-error-700); font-size: var(--syn-font-size-x-large);'
          : '';

      dialog.innerHTML = `
        <p class="text-sm">${this.escapeHtml(message)}</p>
        <syn-button id="dlg-cancel" slot="footer" variant="text">${this.escapeHtml(cancelLabel)}</syn-button>
        <syn-button id="dlg-confirm" slot="footer" variant="outline" style="${confirmStyle}">${this.escapeHtml(confirmLabel)}</syn-button>
      `;

      let settled = false;

      const settle = (result: boolean) => {
        if (settled) return;
        settled = true;
        dialog.hide?.();
        if (dialog.parentNode) document.body.removeChild(dialog);
        resolve(result);
      };

      dialog.addEventListener('syn-request-close', () => settle(false));

      document.body.appendChild(dialog);

      dialog.querySelector('#dlg-cancel')?.addEventListener('click', () => settle(false));
      dialog.querySelector('#dlg-confirm')?.addEventListener('click', () => settle(true));

      dialog.show?.();
    });
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
