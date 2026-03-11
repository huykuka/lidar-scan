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

      const btnVariant = variant === 'danger' ? 'filled' : 'outline';
      const btnClass =
        variant === 'danger' ? 'bg-red-600 hover:bg-red-700 text-white border-red-600' : '';

      dialog.innerHTML = `
        <p class="text-sm text-neutral-700 dark:text-neutral-300">${this.escapeHtml(message)}</p>
        <div slot="footer" class="flex justify-end gap-2">
          <syn-button id="dlg-cancel" variant="outline">${this.escapeHtml(cancelLabel)}</syn-button>
          <syn-button id="dlg-confirm" variant="${btnVariant}" class="${btnClass}">${this.escapeHtml(confirmLabel)}</syn-button>
        </div>
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
