import { inject, Injectable } from '@angular/core';
import { from, Observable, throwError } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { ConfigApiService } from './config-api.service';
import {
  ConfigExport,
  ConfigImportResponse,
  ConfigValidationResponse,
} from '../../models/config.model';

/** Result emitted by {@link ConfigTransferService#uploadConfig} after the file
 *  has been parsed and validated against the backend. */
export interface UploadConfigResult {
  config: ConfigExport;
  validation: ConfigValidationResponse;
}

/** Result emitted by {@link ConfigTransferService#downloadConfig} – a ready-to-use
 *  Blob plus the suggested file name for the browser download. */
export interface DownloadConfigResult {
  blob: Blob;
  filename: string;
}

/**
 * Centralises the HTTP/IO logic for config import (upload) and export (download).
 *
 * ### Responsibilities
 * - Read and JSON-parse an uploaded File.
 * - POST to `/config/validate` and return the result alongside the parsed config.
 * - POST to `/config/import` and return the backend response.
 * - GET `/config/export`, serialise the JSON to a Blob, and derive a filename.
 *
 * ### NOT responsible for
 * - Showing toasts / modals — that stays in the component.
 * - Triggering browser download (anchor click) — that stays in the component.
 */
@Injectable({ providedIn: 'root' })
export class ConfigTransferService {
  private configApi = inject(ConfigApiService);

  // ---------------------------------------------------------------------------
  // Upload / import pipeline
  // ---------------------------------------------------------------------------

  /**
   * Read a JSON `File`, validate it against the backend, and return the parsed
   * config together with the validation result.
   *
   * Errors (file read failure, JSON parse error, HTTP errors) are propagated as
   * Observable errors so the subscriber (component) can react with user feedback.
   */
  readAndValidate(file: File): Observable<UploadConfigResult> {
    return from(file.text()).pipe(
      // Parse JSON — throw a descriptive error on malformed input
      map((text) => {
        try {
          return JSON.parse(text) as ConfigExport;
        } catch {
          throw new Error('Invalid JSON: the selected file is not valid JSON.');
        }
      }),
      // Validate against the backend
      switchMap((config) =>
        from(this.configApi.validateConfig(config)).pipe(
          map((validation) => ({ config, validation })),
        ),
      ),
      catchError((err) => throwError(() => err)),
    );
  }

  /**
   * POST the validated config to the backend import endpoint.
   *
   * @param config  The `ConfigExport` object previously returned by `readAndValidate`.
   * @param merge   When `true` the backend merges into the existing config;
   *                when `false` it replaces it entirely.
   */
  importConfig(config: ConfigExport, merge: boolean): Observable<ConfigImportResponse> {
    return from(this.configApi.importConfig(config, merge)).pipe(
      catchError((err) => throwError(() => err)),
    );
  }

  // ---------------------------------------------------------------------------
  // Download / export pipeline
  // ---------------------------------------------------------------------------

  /**
   * Fetch the current config from the backend, serialise it as a pretty-printed
   * JSON Blob, and derive a dated filename.
   *
   * The component is responsible for triggering the browser download.
   */
  downloadConfig(): Observable<DownloadConfigResult> {
    return from(this.configApi.exportConfig()).pipe(
      map((config) => {
        const blob = new Blob([JSON.stringify(config, null, 2)], {
          type: 'application/json',
        });
        const filename = `lidar-config-${new Date().toISOString().split('T')[0]}.json`;
        return { blob, filename };
      }),
      catchError((err) => throwError(() => err)),
    );
  }
}
