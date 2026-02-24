// dialog.service.ts
import {
  ApplicationRef,
  ComponentFactoryResolver,
  ComponentRef,
  EmbeddedViewRef,
  Injectable,
  Injector,
  Type,
} from '@angular/core';
import { fromEvent, Subject, takeUntil } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class DialogService {
  $close = new Subject<any>();
  private dialogElement: HTMLElement | null = null;
  private childComponentRef: ComponentRef<any> | null = null;
  private destroySubject = new Subject<void>();

  constructor(
    private componentFactoryResolver: ComponentFactoryResolver,
    private appRef: ApplicationRef,
    private injector: Injector,
  ) {
    // Get the root dialog element
    this.dialogElement = document.querySelector('syn-dialog');
    if (!this.dialogElement) {
      console.error('No syn-dialog element found at root level');
    } else {
      // Listen for native dialog close events
      this.setupCloseListener();
    }
  }

  /**
   * Opens the root dialog with a dynamic child component
   * @param component Component to be injected into dialog
   * @param dialogConfig
   * @param componentData
   */
  // dialog.service.ts
  open<T>(component: Type<T>, dialogConfig?: any, componentData?: any): void {
    if (!this.dialogElement) {
      console.error('Dialog element not found');
      return;
    }

    // Clear any existing content in the dialog (except footer)
    const footer = this.dialogElement.querySelector('[slot="footer"]');
    this.dialogElement.innerHTML = '';
    if (footer) {
      this.dialogElement.appendChild(footer);
    }

    // Set attributes on the dialog element
    if (dialogConfig) {
      Object.keys(dialogConfig).forEach((key) => {
        this.dialogElement?.setAttribute(key, dialogConfig[key]);
      });
    }

    // Create and attach component
    const componentRef = this.createComponent(component, componentData);
    this.childComponentRef = componentRef;

    // Append the new component to dialog
    this.dialogElement.insertBefore(
      (componentRef.hostView as EmbeddedViewRef<any>).rootNodes[0],
      footer || null,
    );

    // Show dialog and activate modal
    (this.dialogElement as any).show();
    (this.dialogElement as any).modal?.activateExternal();
  }

  /**
   * Closes the dialog and cleans up resources
   */
  close(): void {
    if (!this.dialogElement) return;

    if (this.childComponentRef) {
      this.appRef.detachView(this.childComponentRef.hostView);
      this.childComponentRef.destroy();
      this.childComponentRef = null;
    }

    (this.dialogElement as any).hide();
    (this.dialogElement as any).modal?.deactivateExternal();
  }

  private setupCloseListener(): void {
    if (!this.dialogElement) return;

    // Listen for the native 'syn-after-hide' event
    fromEvent(this.dialogElement, 'syn-request-close')
      .pipe(takeUntil(this.destroySubject))
      .subscribe((event) => {
        this.handleClose(event);
      });
  }

  private handleClose(event: any): void {
    if (this.childComponentRef) {
      this.appRef.detachView(this.childComponentRef.hostView);
      this.childComponentRef.destroy();
      this.childComponentRef = null;
    }

    (this.dialogElement as any).hide();
    (this.dialogElement as any).modal?.deactivateExternal();

    // Emit close event with any data
    this.$close.next(event);
  }

  /**
   * Creates a component dynamically
   */
  private createComponent<T>(component: Type<T>, data?: any): ComponentRef<T> {
    const componentFactory = this.componentFactoryResolver.resolveComponentFactory(component);
    const componentRef: any = componentFactory.create(this.injector);

    // Pass data to component if provided
    if (data) {
      Object.assign(componentRef.instance, data);
    }

    this.appRef.attachView(componentRef.hostView);
    return componentRef;
  }
}
