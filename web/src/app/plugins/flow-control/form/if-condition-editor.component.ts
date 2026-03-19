import { Component, computed, CUSTOM_ELEMENTS_SCHEMA, effect, inject, OnDestroy, OnInit, output, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';
import { SynergyComponentsModule } from '@synergy-design-system/angular';
import { NodeEditorComponent } from '@core/models/node-plugin.model';
import { NodeStoreService } from '@core/services/stores/node-store.service';
import { ToastService } from '@core/services/toast.service';
import { NodeEditorHeaderComponent } from '@plugins/shared/node-editor-header/node-editor-header.component';
import { environment } from '@env/environment';

/**
 * Editor component for configuring IF Condition nodes
 * Provides expression editor with validation and external control URL display
 */
@Component({
  selector: 'app-if-condition-editor',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  imports: [ReactiveFormsModule, SynergyComponentsModule, NodeEditorHeaderComponent],
  templateUrl: './if-condition-editor.component.html',
  styleUrl: './if-condition-editor.component.css',
})
export class IfConditionEditorComponent implements OnInit, OnDestroy, NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();
  
  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  
  form!: FormGroup;
  validationError = signal<string | null>(null);
  protected isSaving = signal(false);
  private expressionSub?: Subscription;
  
  /**
   * Check if we're editing an existing node (has ID) or creating new
   */
  protected isEditMode = computed(() => this.nodeStore.select('editMode')());
  
  /**
   * Current node ID (null if creating new node)
   */
  protected nodeId = computed(() => this.nodeStore.selectedNode()?.id ?? null);
  
  /**
   * Computed URL for setting external state
   */
  protected setUrl = computed(() =>
    this.nodeId()
      ? `${environment.apiUrl}/nodes/${this.nodeId()}/flow-control/set`
      : null
  );
  
  /**
   * Computed URL for resetting external state
   */
  protected resetUrl = computed(() =>
    this.nodeId()
      ? `${environment.apiUrl}/nodes/${this.nodeId()}/flow-control/reset`
      : null
  );

  constructor() {
    // Initialize form in constructor (injection context)
    const node = this.nodeStore.selectedNode();
    
    this.form = new FormGroup({
      name: new FormControl(node?.name || 'If Condition', [Validators.required]),
      expression: new FormControl(
        node?.config?.['expression'] || 'true',
        [Validators.required]
      ),
      throttle_ms: new FormControl(node?.config?.['throttle_ms'] || 0)
    });
    
    // Subscribe to expression changes for real-time validation
    const expressionControl = this.form.get('expression');
    if (expressionControl) {
      this.expressionSub = expressionControl.valueChanges.subscribe(expr => {
        this.validateExpression(expr);
      });
      // Validate initial value
      this.validateExpression(expressionControl.value);
    }
  }

  ngOnInit(): void {
    // NgOnInit kept for interface compliance
  }

  ngOnDestroy(): void {
    this.expressionSub?.unsubscribe();
  }
  
  /**
   * Validate expression syntax on client side
   */
  private validateExpression(expr: string): void {
    if (!expr || expr.trim() === '') {
      this.validationError.set('Expression cannot be empty');
      return;
    }
    
    // Check for allowed characters only
    const allowedPattern = /^[a-z_0-9\s><=!&|()\.]+$/i;
    if (!allowedPattern.test(expr)) {
      this.validationError.set('Invalid characters in expression');
      return;
    }
    
    // Check for balanced parentheses
    let depth = 0;
    for (const char of expr) {
      if (char === '(') depth++;
      if (char === ')') depth--;
      if (depth < 0) {
        this.validationError.set('Unbalanced parentheses');
        return;
      }
    }
    if (depth !== 0) {
      this.validationError.set('Unbalanced parentheses');
      return;
    }
    
    this.validationError.set(null);
  }
  
  /**
   * Save form data to node store
   */
  onSave(): void {
    if (!this.form.valid) {
      this.toast.warning('Please fix validation errors before saving');
      return;
    }
    
    const node = this.nodeStore.selectedNode();
    const updated = {
      ...node,
      name: this.form.value.name,
      config: {
        ...node.config,
        expression: this.form.value.expression,
        throttle_ms: this.form.value.throttle_ms
      }
    };
    
    this.nodeStore.setState({ selectedNode: updated });
    this.saved.emit();
  }
  
  /**
   * Cancel editing
   */
  onCancel(): void {
    this.cancelled.emit();
  }
  
  /**
   * Copy text to clipboard and show toast
   */
  protected copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.toast.success('URL copied to clipboard');
    }).catch((err) => {
      console.error('Failed to copy to clipboard:', err);
      this.toast.danger('Failed to copy to clipboard');
    });
  }
}
