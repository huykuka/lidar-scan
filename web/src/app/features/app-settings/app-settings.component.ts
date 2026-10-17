import {ChangeDetectionStrategy, Component, computed, inject, OnInit, signal} from '@angular/core';
import {HttpErrorResponse} from '@angular/common/http';
import {SynergyComponentsModule} from '@synergy-design-system/angular';
import {AuthService} from '@core/services/auth.service';
import {NavigationService} from '@core/services/navigation.service';
import {SystemStatusService} from '@core/services/system-status.service';
import {Theme, ThemeService} from '@core/services/theme.service';
import {ToastService} from '@core/services/toast.service';
import {
  AppSetting,
  AppSettingCategory,
  AppSettingsApiService,
  SettingValue,
  StorageTestResult,
} from '@core/services/api/app-settings-api.service';

const MINIMAP_KEY = 'flow-canvas.minimapVisible';
const LIVE_STATUS_KEY = 'flow-canvas.liveStatus';
/** Browser-side caches that can be safely rebuilt. Auth and theme are intentionally excluded. */
const LOCAL_DATA_KEYS = ['lidar_split_layout_v1', 'lidar_workspace_settings'];

interface NavEntry {
  id: string;
  label: string;
  icon: string;
  description: string;
  /** Needs the backend settings API (service only) */
  backend: boolean;
}

const APPEARANCE: NavEntry = {
  id: 'appearance', label: 'Appearance', icon: 'palette', backend: false,
  description: 'Theme and editor preferences. Stored in this browser only.',
};
const ACCOUNT: NavEntry = {
  id: 'account', label: 'Account', icon: 'person', backend: false,
  description: 'The user you are signed in as.',
};
const ABOUT: NavEntry = {
  id: 'about', label: 'About', icon: 'info', backend: false,
  description: 'Backend status and version.',
};

@Component({
  selector: 'app-app-settings',
  imports: [SynergyComponentsModule],
  templateUrl: './app-settings.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppSettingsComponent implements OnInit {
  private navService = inject(NavigationService);
  private toast = inject(ToastService);
  private api = inject(AppSettingsApiService);
  protected theme = inject(ThemeService);
  protected auth = inject(AuthService);
  protected status = inject(SystemStatusService);

  // ── Browser-side preferences ────────────────────────────────────────────
  protected readonly minimapVisible = signal(localStorage.getItem(MINIMAP_KEY) !== 'false');
  protected readonly liveStatus = signal(localStorage.getItem(LIVE_STATUS_KEY) !== 'false');

  // ── Backend settings ────────────────────────────────────────────────────
  protected readonly categories = signal<AppSettingCategory[]>([]);
  protected readonly encryptionAvailable = signal(true);
  protected readonly encryptionError = signal<string | null>(null);
  protected readonly loading = signal(false);
  protected readonly loadError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly fieldErrors = signal<Record<string, string>>({});
  /** Unsaved edits, keyed by setting key */
  protected readonly draft = signal<Record<string, SettingValue>>({});
  /** Keys the user chose to revert to their default on save */
  protected readonly resets = signal<ReadonlySet<string>>(new Set());
  /** Secret keys currently being edited */
  protected readonly editingSecrets = signal<ReadonlySet<string>>(new Set());
  protected readonly testing = signal(false);
  protected readonly testResult = signal<StorageTestResult | null>(null);

  protected readonly activeId = signal('appearance');


  protected readonly navEntries = computed<NavEntry[]>(() => [
    APPEARANCE,
    ...this.categories().map((c) => ({
      id: c.id, label: c.label, icon: c.icon, description: c.description, backend: true,
    })),
    ACCOUNT,
    ABOUT,
  ]);
  protected readonly activeEntry = computed(
    () => this.navEntries().find((e) => e.id === this.activeId()) ?? APPEARANCE,
  );
  protected readonly activeCategory = computed(
    () => this.categories().find((c) => c.id === this.activeId()) ?? null,
  );

  protected readonly dirtyKeys = computed(() => {
    const keys = new Set(Object.keys(this.draft()));
    this.resets().forEach((k) => keys.add(k));
    return keys;
  });
  protected readonly dirtyCount = computed(() => this.dirtyKeys().size);

  /** Dirty count per category, shown as a dot in the nav */
  protected readonly dirtyByCategory = computed(() => {
    const dirty = this.dirtyKeys();
    const out: Record<string, number> = {};
    for (const c of this.categories()) {
      out[c.id] = c.settings.filter((s) => dirty.has(s.key)).length;
    }
    return out;
  });

  protected readonly retentionWarning = computed(() => {
    const days = Number(this.valueOf('RETENTION_RECORDINGS_DAYS'));
    return days > 0 && this.valueOf('RETENTION_ONLY_UPLOADED') === false;
  });

  ngOnInit(): void {
    this.navService.setPageConfig({
      title: 'App Settings',
      subtitle: 'Appearance, storage and data retention',
    });
    if (this.auth.isService()) void this.load();
  }

  // ── Loading / saving ────────────────────────────────────────────────────

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const res = await this.api.get();
      this.categories.set(res.categories);
      this.encryptionAvailable.set(res.encryption_available);
      this.encryptionError.set(res.encryption_error);
    } catch (e) {
      this.loadError.set(this.describe(e, 'Could not load settings from the backend.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected async save(): Promise<void> {
    const resets = this.resets();
    const values: Record<string, SettingValue> = {};
    for (const [key, value] of Object.entries(this.draft())) {
      if (!resets.has(key)) values[key] = value;
    }
    this.saving.set(true);
    this.fieldErrors.set({});
    try {
      const res = await this.api.update(values, [...resets]);
      this.categories.set(res.categories);
      this.encryptionAvailable.set(res.encryption_available);
      this.encryptionError.set(res.encryption_error);
      this.draft.set({});
      this.resets.set(new Set());
      this.editingSecrets.set(new Set());
      this.testResult.set(null);
      this.toast.success('Settings saved');
    } catch (e) {
      const detail = (e as HttpErrorResponse)?.error?.detail;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        this.fieldErrors.set(detail as Record<string, string>);
        this.toast.danger('Some settings are invalid. Check the highlighted fields.');
      } else {
        this.toast.danger(this.describe(e, 'Could not save settings.'));
      }
    } finally {
      this.saving.set(false);
    }
  }

  protected discard(): void {
    this.draft.set({});
    this.resets.set(new Set());
    this.editingSecrets.set(new Set());
    this.fieldErrors.set({});
  }

  protected async testStorage(): Promise<void> {
    this.testing.set(true);
    this.testResult.set(null);
    try {
      this.testResult.set(await this.api.testStorage());
    } catch (e) {
      this.toast.danger(this.describe(e, 'Could not test the storage connection.'));
    } finally {
      this.testing.set(false);
    }
  }

  // ── Field helpers ───────────────────────────────────────────────────────

  protected valueOf(key: string): SettingValue {
    const draft = this.draft();
    if (key in draft) return draft[key];
    for (const c of this.categories()) {
      const s = c.settings.find((x) => x.key === key);
      if (s) return s.value;
    }
    return null;
  }

  protected isDirty(s: AppSetting): boolean {
    return this.dirtyKeys().has(s.key);
  }

  protected isDisabled(s: AppSetting): boolean {
    if (!s.depends_on) return false;
    return !this.valueOf(s.depends_on);
  }

  protected canReset(s: AppSetting): boolean {
    if (s.type === 'secret') return false;
    if (this.resets().has(s.key)) return false;
    return s.modified && this.valueOf(s.key) !== s.default;
  }

  protected setValue(s: AppSetting, value: SettingValue): void {
    this.fieldErrors.update((e) => this.without(e, s.key));
    this.resets.update((r) => {
      const next = new Set(r);
      next.delete(s.key);
      return next;
    });
    this.draft.update((d) => {
      if (s.type !== 'secret' && value === s.value) return this.without(d, s.key);
      return {...d, [s.key]: value};
    });
  }

  protected onText(s: AppSetting, event: Event): void {
    this.setValue(s, (event.target as HTMLInputElement).value);
  }

  protected onNumber(s: AppSetting, event: Event): void {
    const raw = (event.target as HTMLInputElement).value;
    const n = Number(raw);
    this.setValue(s, raw.trim() === '' || !Number.isInteger(n) ? raw : n);
  }

  protected onBool(s: AppSetting, event: Event): void {
    this.setValue(s, (event.target as HTMLInputElement).checked);
  }

  protected onSelect(s: AppSetting, event: Event): void {
    this.setValue(s, (event.target as HTMLSelectElement).value);
  }

  protected resetToDefault(s: AppSetting): void {
    this.draft.update((d) => ({...d, [s.key]: s.default}));
    this.resets.update((r) => new Set(r).add(s.key));
    this.fieldErrors.update((e) => this.without(e, s.key));
  }

  protected editSecret(s: AppSetting): void {
    this.editingSecrets.update((set) => new Set(set).add(s.key));
  }

  protected cancelSecret(s: AppSetting): void {
    this.editingSecrets.update((set) => {
      const next = new Set(set);
      next.delete(s.key);
      return next;
    });
    this.draft.update((d) => this.without(d, s.key));
  }

  protected isEditingSecret(s: AppSetting): boolean {
    return !s.is_set || this.editingSecrets().has(s.key);
  }

  // ── Browser-side handlers ───────────────────────────────────────────────

  protected onThemeChange(event: Event): void {
    this.theme.setTheme((event.target as HTMLInputElement).value as Theme);
  }

  protected onMinimapChange(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.minimapVisible.set(checked);
    localStorage.setItem(MINIMAP_KEY, String(checked));
  }

  protected onLiveStatusChange(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.liveStatus.set(checked);
    localStorage.setItem(LIVE_STATUS_KEY, String(checked));
  }

  protected resetLocalData(): void {
    LOCAL_DATA_KEYS.forEach((key) => localStorage.removeItem(key));
    this.toast.success('Saved layouts cleared. Reload the page to apply.');
  }

  protected select(id: string): void {
    this.activeId.set(id);
  }

  private without<T>(obj: Record<string, T>, key: string): Record<string, T> {
    const {[key]: _removed, ...rest} = obj;
    return rest;
  }

  private describe(e: unknown, fallback: string): string {
    const err = e as HttpErrorResponse;
    if (err?.status === 401 || err?.status === 403) return 'Service access is required to change these settings.';
    const detail = err?.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
