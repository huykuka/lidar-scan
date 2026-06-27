import {
  Component,
  inject,
  computed,
  ViewContainerRef,
  effect,
  ChangeDetectionStrategy,
  signal,
  DestroyRef,
  viewChild
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl } from '@angular/forms';
import {
  SynDrawerComponent,
  SynButtonComponent,
  SynIconComponent,
} from '@synergy-design-system/angular';
import { DrawerService } from '@core/services/drawer.service';

@Component({
  selector: 'app-drawer-host',
  imports: [SynDrawerComponent, SynButtonComponent, SynIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: [
    `
      :host {
        --guide-border: color-mix(in srgb, var(--syn-color-neutral-300) 80%, transparent);
      }
      .drawer-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--syn-spacing-medium) var(--syn-spacing-large);
        border-bottom: 1px solid var(--guide-border);
        background: linear-gradient(
          180deg,
          color-mix(in srgb, var(--syn-color-primary-50) 70%, white),
          var(--syn-color-neutral-25)
        );
      }
      .drawer-title {
        font-size: var(--syn-font-size-large);
        font-weight: var(--syn-font-weight-bold);
        color: var(--syn-typography-color-text);
        margin: 0;
      }
      .drawer-body {
        padding: var(--syn-spacing-small) var(--syn-spacing-medium) var(--syn-spacing-medium);
      }
      .drawer-title-wrap {
        display: flex;
        align-items: center;
        gap: var(--syn-spacing-small);
      }
    `,
  ],
  template: `
    <syn-drawer
      label=" "
      no-header
      [open]="svc.isOpen()"
      [placement]="svc.placement()"
      [style]="sizeStyle()"
      (syn-request-close)="onRequestClose($event)"
    >
      <!-- Custom header -->
      <div class="drawer-header">
        <div class="drawer-title-wrap">
          <syn-icon name="info" aria-hidden="true" />
          <h2 class="drawer-title">{{ svc.title() }}</h2>
        </div>
        <syn-button variant="text" size="small" (click)="svc.close()">
          <syn-icon slot="prefix" name="close" aria-hidden="true" />Close
        </syn-button>
      </div>

      <!-- Dynamic content -->
      <div class="drawer-body">
        <ng-container #outlet />
      </div>

      @if (svc.showFooter()) {
        <!-- Footer: Cancel + Save -->
        <div slot="footer" class="flex justify-end gap-2 w-full">
          <syn-button variant="outline" (click)="svc.close()"
            ><syn-icon slot="prefix" name="close" aria-hidden="true" />Cancel</syn-button
          >
          <syn-button variant="filled" [disabled]="formInvalid()" (click)="submitForm()"
            ><syn-icon slot="prefix" name="save" aria-hidden="true" />Save</syn-button
          >
        </div>
      }
    </syn-drawer>
  `,
})
export class DrawerHostComponent {
  protected readonly svc = inject(DrawerService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly outlet = viewChild.required('outlet', { read: ViewContainerRef });

  private formInstance: Record<string, unknown> | null = null;

  /** true = save button disabled. Starts false (enabled) until a form with a FormGroup loads */
  protected readonly formInvalid = signal(false);

  protected readonly sizeStyle = computed(() => {
    const s = this.svc.size();
    return s ? `--size: ${s}` : '';
  });

  protected onRequestClose(event: Event): void {
    event.preventDefault();
  }

  protected submitForm(): void {
    const form = this.outlet().element.nativeElement?.parentElement?.querySelector(
      'form',
    ) as HTMLFormElement | null;
    if (form) {
      form.requestSubmit();
    } else if (this.formInstance && typeof this.formInstance['onSubmit'] === 'function') {
      (this.formInstance['onSubmit'] as () => void)();
    }
  }

  constructor() {
    effect(() => {
      const component = this.svc.component();
      const inputs = this.svc.inputs();

      this.outlet().clear();
      this.formInstance = null;
      this.formInvalid.set(false); // reset on each open

      if (!component) return;

      const ref = this.outlet().createComponent(component);
      Object.entries(inputs).forEach(([key, value]) => {
        ref.setInput(key, value);
      });
      ref.changeDetectorRef.detectChanges();

      this.formInstance = ref.instance as Record<string, unknown>;

      // Find the first AbstractControl (FormGroup) on the component instance
      const formGroup = this.findFormGroup(this.formInstance);
      if (formGroup) {
        // Set initial state
        this.formInvalid.set(formGroup.invalid);

        // Track validity changes reactively
        formGroup.statusChanges
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.formInvalid.set(formGroup.invalid));
      }
    });
  }

  /**
   * Walk the component instance's own properties looking for an AbstractControl.
   * Covers itemForm, userForm, roleForm, gmailForm, sesForm, etc.
   */
  private findFormGroup(instance: Record<string, unknown>): AbstractControl | null {
    for (const key of Object.keys(instance)) {
      const val = instance[key];
      if (val instanceof AbstractControl) {
        return val;
      }
    }
    return null;
  }
}
