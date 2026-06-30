import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { setGlobalDefaultSettings } from '@synergy-design-system/components';

import * as THREE from 'three';

// Polyfill crypto.randomUUID for non-secure contexts (HTTP on LAN IPs).
// angular-three calls crypto.randomUUID() to assign __ngt_id__ to every scene
// object. Browsers only expose randomUUID on secure contexts (HTTPS / localhost),
// so LAN access over plain HTTP silently breaks the 3D renderer.
if (typeof crypto !== 'undefined' && typeof crypto.randomUUID !== 'function') {
  (crypto as any).randomUUID = function (): string {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
  };
}

// Set size="small" globally for all Synergy components that support it
setGlobalDefaultSettings({
  size: {
    SynAccordion: 'small',
    SynAlert: 'small',
    SynButton: 'small',
    SynButtonGroup: 'small',
    SynCheckbox: 'small',
    SynCombobox: 'small',
    SynDetails: 'small',
    SynFile: 'small',
    SynIconButton: 'small',
    SynInput: 'small',
    SynPagination: 'small',
    SynRadio: 'small',
    SynRadioButton: 'small',
    SynRadioGroup: 'small',
    SynRange: 'small',
    SynSelect: 'small',
    SynSwitch: 'small',
    SynTag: 'small',
    SynTagGroup: 'small',
    SynTextarea: 'small',
  },
});

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
