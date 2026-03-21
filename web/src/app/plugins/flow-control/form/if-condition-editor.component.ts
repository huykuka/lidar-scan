import {Component, computed, inject, OnDestroy, OnInit, output, signal} from '@angular/core';
import {FormControl, FormGroup, ReactiveFormsModule, Validators} from '@angular/forms';
import {Subscription} from 'rxjs';
import {SynergyComponentsModule, SynergyFormsModule} from '@synergy-design-system/angular';
import {NodeEditorComponent} from '@core/models/node-plugin.model';
import {NodeStoreService} from '@core/services/stores/node-store.service';
import {ToastService} from '@core/services/toast.service';
import {NodeEditorHeaderComponent} from '@plugins/shared/node-editor-header/node-editor-header.component';
import {NodeEditorFacadeService} from '@features/settings/services/node-editor-facade.service';
import {environment} from '@env/environment';
import {CommonModule} from '@angular/common';

/**
 * Autocomplete suggestion item
 */
interface AutocompleteSuggestion {
  label: string;
  type: 'variable' | 'operator' | 'keyword' | 'value';
  description: string;
  insertText?: string; // Optional: different text to insert vs display
}

/**
 * Editor component for configuring IF Condition nodes
 * Provides expression editor with validation and external control URL display
 */
@Component({
  selector: 'app-if-condition-editor',
  standalone: true,

  imports: [ReactiveFormsModule, SynergyComponentsModule, NodeEditorHeaderComponent, SynergyFormsModule, CommonModule],
  providers: [NodeEditorFacadeService],
  templateUrl: './if-condition-editor.component.html',
  styleUrl: './if-condition-editor.component.css',
})
export class IfConditionEditorComponent implements OnInit, OnDestroy, NodeEditorComponent {
  saved = output<void>();
  cancelled = output<void>();

  private nodeStore = inject(NodeStoreService);
  private toast = inject(ToastService);
  private facade = inject(NodeEditorFacadeService);

  form!: FormGroup;
  validationError = signal<string | null>(null);
  protected isSaving = signal(false);
  private expressionSub?: Subscription;

  // Autocomplete state
  protected showAutocomplete = signal(false);
  protected autocompleteSuggestions = signal<AutocompleteSuggestion[]>([]);
  protected selectedSuggestionIndex = signal(0);
  protected cursorPosition = signal(0);

  /**
   * Available variables for autocomplete
   */
  private readonly VARIABLES: AutocompleteSuggestion[] = [
    { label: 'point_count', type: 'variable', description: 'Number of points in the point cloud' },
    { label: 'intensity', type: 'variable', description: 'Intensity value (sensor-specific)' },
    { label: 'external_state', type: 'variable', description: 'External override state (boolean or null)' },
    { label: 'x', type: 'variable', description: 'X coordinate (Cartesian)' },
    { label: 'y', type: 'variable', description: 'Y coordinate (Cartesian)' },
    { label: 'z', type: 'variable', description: 'Z coordinate (Cartesian)' },
    { label: 'azimuth', type: 'variable', description: 'Azimuth angle (polar)' },
    { label: 'elevation', type: 'variable', description: 'Elevation angle (polar)' },
    { label: 'range', type: 'variable', description: 'Range distance (polar)' },
    { label: 'layer', type: 'variable', description: 'Scanner layer index' },
    { label: 'echo', type: 'variable', description: 'Echo return index' },
    { label: 'reflector', type: 'variable', description: 'Reflector flag (boolean)' },
  ];

  /**
   * Available operators for autocomplete
   */
  private readonly OPERATORS: AutocompleteSuggestion[] = [
    { label: '>', type: 'operator', description: 'Greater than', insertText: ' > ' },
    { label: '<', type: 'operator', description: 'Less than', insertText: ' < ' },
    { label: '==', type: 'operator', description: 'Equal to', insertText: ' == ' },
    { label: '!=', type: 'operator', description: 'Not equal to', insertText: ' != ' },
    { label: '>=', type: 'operator', description: 'Greater than or equal to', insertText: ' >= ' },
    { label: '<=', type: 'operator', description: 'Less than or equal to', insertText: ' <= ' },
  ];

  /**
   * Available keywords for autocomplete
   */
  private readonly KEYWORDS: AutocompleteSuggestion[] = [
    { label: 'AND', type: 'keyword', description: 'Logical AND operator', insertText: ' AND ' },
    { label: 'OR', type: 'keyword', description: 'Logical OR operator', insertText: ' OR ' },
    { label: 'NOT', type: 'keyword', description: 'Logical NOT operator', insertText: 'NOT ' },
    { label: 'true', type: 'value', description: 'Boolean true value' },
    { label: 'false', type: 'value', description: 'Boolean false value' },
  ];

  /**
   * All available suggestions combined
   */
  private readonly ALL_SUGGESTIONS = [
    ...this.VARIABLES,
    ...this.OPERATORS,
    ...this.KEYWORDS,
  ];

  /**
   * Get node definition for the IF condition type
   */
  protected definition = computed(() => {
    return this.nodeStore.nodeDefinitions().find((d) => d.type === 'if_condition');
  });

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
      use_external_control: new FormControl(node?.config?.['use_external_control'] || false)
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
   * Handle input events on expression textarea
   */
  protected onExpressionInput(event: Event): void {
    const textarea = event.target as HTMLTextAreaElement;
    const value = textarea.value;
    const cursorPos = textarea.selectionStart;

    this.cursorPosition.set(cursorPos);

    // Get word at cursor for autocomplete
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastWord = this.getLastWord(textBeforeCursor);

    if (lastWord.length > 0) {
      this.updateAutocomplete(lastWord);
    } else {
      this.showAutocomplete.set(false);
    }
  }

  /**
   * Handle keydown events for autocomplete navigation
   */
  protected onExpressionKeydown(event: KeyboardEvent): void {
    if (!this.showAutocomplete()) return;

    const suggestions = this.autocompleteSuggestions();

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.selectedSuggestionIndex.update(idx =>
          Math.min(idx + 1, suggestions.length - 1)
        );
        break;

      case 'ArrowUp':
        event.preventDefault();
        this.selectedSuggestionIndex.update(idx => Math.max(idx - 1, 0));
        break;

      case 'Enter':
      case 'Tab':
        event.preventDefault();
        this.insertSuggestion(suggestions[this.selectedSuggestionIndex()], event);
        break;

      case 'Escape':
        event.preventDefault();
        this.showAutocomplete.set(false);
        break;
    }
  }

  /**
   * Get the last partial word before cursor
   */
  private getLastWord(text: string): string {
    // Match word characters and underscores
    const match = text.match(/[a-z_][a-z0-9_]*$/i);
    return match ? match[0] : '';
  }

  /**
   * Update autocomplete suggestions based on partial input
   */
  private updateAutocomplete(partial: string): void {
    const lower = partial.toLowerCase();

    const filtered = this.ALL_SUGGESTIONS.filter(s =>
      s.label.toLowerCase().startsWith(lower)
    );

    if (filtered.length > 0) {
      this.autocompleteSuggestions.set(filtered);
      this.selectedSuggestionIndex.set(0);
      this.showAutocomplete.set(true);
    } else {
      this.showAutocomplete.set(false);
    }
  }

  /**
   * Insert selected suggestion into expression
   */
  protected insertSuggestion(suggestion: AutocompleteSuggestion, event?: Event): void {
    // Get the textarea element - try from event or fall back to DOM query
    let textarea: HTMLTextAreaElement | null = null;

    if (event) {
      const target = event.target as HTMLElement;
      textarea = target.closest('.expression-container')?.querySelector('textarea') || null;
    }

    if (!textarea) {
      // Fallback: query the DOM directly
      textarea = document.querySelector('.expression-container textarea');
    }

    if (!textarea) return;

    const value = this.form.get('expression')?.value || '';
    const cursorPos = textarea.selectionStart;
    const textBeforeCursor = value.substring(0, cursorPos);
    const textAfterCursor = value.substring(cursorPos);

    // Find start of current word
    const lastWord = this.getLastWord(textBeforeCursor);
    const startPos = cursorPos - lastWord.length;

    // Insert suggestion
    const insertText = suggestion.insertText || suggestion.label;
    const newValue = value.substring(0, startPos) + insertText + textAfterCursor;
    const newCursorPos = startPos + insertText.length;

    // Update form control
    this.form.get('expression')?.setValue(newValue);

    // Update cursor position
    setTimeout(() => {
      textarea?.setSelectionRange(newCursorPos, newCursorPos);
      textarea?.focus();
    }, 0);

    this.showAutocomplete.set(false);
  }

  /**
   * Handle click on autocomplete suggestion
   */
  protected onSuggestionClick(suggestion: AutocompleteSuggestion, event: Event): void {
    this.insertSuggestion(suggestion, event);
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
   * Save form data to backend via facade service
   */
  async onSave(): Promise<void> {
    if (!this.form.valid || this.validationError()) {
      this.toast.warning('Please fix validation errors before saving');
      return;
    }

    const def = this.definition();
    if (!def) {
      this.toast.danger('Node definition not found');
      return;
    }

    this.isSaving.set(true);

    const success = await this.facade.saveNode({
      name: this.form.value.name,
      config: {
        expression: this.form.value.expression,
        throttle_ms: 0, // Always 0, no throttling for IF logic
        use_external_control: this.form.value.use_external_control
      },
      definition: def,
      existingNode: this.nodeStore.selectedNode(),
    });

    this.isSaving.set(false);

    if (success) {
      this.saved.emit();
    }
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
