import {Injectable, signal, Type} from '@angular/core';

export interface DrawerConfig<T = unknown> {
  /** Title shown in the drawer header */
  title?: string;
  /** Placement of the drawer: 'end' (default), 'start', 'top', 'bottom' */
  placement?: 'end' | 'start' | 'top' | 'bottom';
  /** CSS custom property for drawer size, e.g. '480px' or '40vw' */
  size?: string;
  /** Optional inputs to pass to the child component */
  inputs?: Partial<Record<keyof T, unknown>>;
  /** Whether to render the default footer actions (Cancel/Save). Defaults to true. */
  showFooter?: boolean;
  /** Called after the drawer has fully closed */
  onClose?: () => void;
}

export interface DrawerRef {
  close: () => void;
}

@Injectable({ providedIn: 'root' })
export class DrawerService {
  readonly isOpen = signal(false);
  readonly title = signal('');
  readonly placement = signal<'end' | 'start' | 'top' | 'bottom'>('end');
  readonly size = signal<string | null>(null);
  readonly showFooter = signal(true);

  private _component = signal<Type<unknown> | null>(null);
  private _inputs = signal<Record<string, unknown>>({});
  private _onClose: (() => void) | undefined;

  readonly component = this._component.asReadonly();
  readonly inputs = this._inputs.asReadonly();

  open<T>(component: Type<T>, config: DrawerConfig<T> = {}): DrawerRef {
    this._component.set(component as Type<unknown>);
    this._inputs.set((config.inputs ?? {}) as Record<string, unknown>);
    this.title.set(config.title ?? '');
    this.placement.set(config.placement ?? 'end');
    this.size.set(config.size ?? null);
    this.showFooter.set(config.showFooter ?? true);
    this._onClose = config.onClose;
    this.isOpen.set(true);

    return { close: () => this.close() };
  }

  close(): void {
    this.isOpen.set(false);
    setTimeout(() => {
      this._component.set(null);
      this._inputs.set({});
      this.showFooter.set(true);
      this._onClose?.();
      this._onClose = undefined;
    }, 300);
  }
}
