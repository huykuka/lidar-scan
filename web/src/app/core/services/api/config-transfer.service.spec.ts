import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { firstValueFrom } from 'rxjs';

import { ConfigTransferService } from './config-transfer.service';
import { ConfigApiService } from './config-api.service';
import { ConfigExport, ConfigImportResponse, ConfigValidationResponse } from '../../models/config.model';

// ---------------------------------------------------------------------------
// JSDOM polyfills — Blob.text() and File.text() are not available in JSDOM
// ---------------------------------------------------------------------------
if (typeof Blob !== 'undefined' && !Blob.prototype.text) {
  Blob.prototype.text = function (): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsText(this);
    });
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MOCK_CONFIG: ConfigExport = {
  version: '1.0',
  lidars: [],
  fusions: [],
};

const MOCK_VALIDATION_OK: ConfigValidationResponse = {
  valid: true,
  errors: [],
  warnings: [],
  summary: { lidars: 0, fusions: 0 },
};

const MOCK_VALIDATION_ERR: ConfigValidationResponse = {
  valid: false,
  errors: ['Missing field: version'],
  warnings: [],
  summary: { lidars: 0, fusions: 0 },
};

const MOCK_IMPORT_RESPONSE: ConfigImportResponse = {
  success: true,
  mode: 'replace',
  imported: { lidars: 2, fusions: 1 },
  lidar_ids: ['l1', 'l2'],
  fusion_ids: ['f1'],
};

function makeJsonFile(data: object, name = 'config.json'): File {
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' });
  return new File([blob], name, { type: 'application/json' });
}

// ---------------------------------------------------------------------------

describe('ConfigTransferService', () => {
  let service: ConfigTransferService;
  let configApiSpy: {
    exportConfig: ReturnType<typeof vi.fn>;
    validateConfig: ReturnType<typeof vi.fn>;
    importConfig: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    configApiSpy = {
      exportConfig: vi.fn(),
      validateConfig: vi.fn(),
      importConfig: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ConfigApiService, useValue: configApiSpy },
      ],
    });

    service = TestBed.inject(ConfigTransferService);
  });

  // -------------------------------------------------------------------------
  // readAndValidate
  // -------------------------------------------------------------------------

  describe('readAndValidate()', () => {
    it('reads a JSON file, calls validateConfig, and returns config + validation', async () => {
      configApiSpy.validateConfig.mockResolvedValue(MOCK_VALIDATION_OK);

      const file = makeJsonFile(MOCK_CONFIG);
      const result = await firstValueFrom(service.readAndValidate(file));

      expect(configApiSpy.validateConfig).toHaveBeenCalledWith(MOCK_CONFIG);
      expect(result.config).toEqual(MOCK_CONFIG);
      expect(result.validation).toEqual(MOCK_VALIDATION_OK);
    });

    it('propagates a validation response with valid=false without throwing', async () => {
      configApiSpy.validateConfig.mockResolvedValue(MOCK_VALIDATION_ERR);

      const file = makeJsonFile(MOCK_CONFIG);
      const result = await firstValueFrom(service.readAndValidate(file));

      expect(result.validation.valid).toBe(false);
      expect(result.validation.errors).toContain('Missing field: version');
    });

    it('throws when the file contains invalid JSON', async () => {
      const invalidBlob = new Blob(['NOT { json }'], { type: 'application/json' });
      const invalidFile = new File([invalidBlob], 'bad.json', { type: 'application/json' });

      await expect(firstValueFrom(service.readAndValidate(invalidFile))).rejects.toThrow(
        /invalid json/i,
      );
      expect(configApiSpy.validateConfig).not.toHaveBeenCalled();
    });

    it('propagates HTTP errors from validateConfig', async () => {
      const httpError = new Error('HTTP 500');
      configApiSpy.validateConfig.mockRejectedValue(httpError);

      const file = makeJsonFile(MOCK_CONFIG);
      await expect(firstValueFrom(service.readAndValidate(file))).rejects.toThrow('HTTP 500');
    });
  });

  // -------------------------------------------------------------------------
  // importConfig
  // -------------------------------------------------------------------------

  describe('importConfig()', () => {
    it('delegates to configApi.importConfig with correct arguments', async () => {
      configApiSpy.importConfig.mockResolvedValue(MOCK_IMPORT_RESPONSE);

      const result = await firstValueFrom(service.importConfig(MOCK_CONFIG, false));

      expect(configApiSpy.importConfig).toHaveBeenCalledWith(MOCK_CONFIG, false);
      expect(result).toEqual(MOCK_IMPORT_RESPONSE);
    });

    it('passes merge=true to the API when requested', async () => {
      configApiSpy.importConfig.mockResolvedValue({ ...MOCK_IMPORT_RESPONSE, mode: 'merge' });

      await firstValueFrom(service.importConfig(MOCK_CONFIG, true));

      expect(configApiSpy.importConfig).toHaveBeenCalledWith(MOCK_CONFIG, true);
    });

    it('propagates HTTP errors from importConfig', async () => {
      configApiSpy.importConfig.mockRejectedValue(new Error('HTTP 422'));

      await expect(firstValueFrom(service.importConfig(MOCK_CONFIG, false))).rejects.toThrow(
        'HTTP 422',
      );
    });
  });

  // -------------------------------------------------------------------------
  // downloadConfig
  // -------------------------------------------------------------------------

  describe('downloadConfig()', () => {
    it('returns a Blob with application/json content type', async () => {
      configApiSpy.exportConfig.mockResolvedValue(MOCK_CONFIG);

      const result = await firstValueFrom(service.downloadConfig());

      expect(result.blob).toBeInstanceOf(Blob);
      expect(result.blob.type).toBe('application/json');
    });

    it('serialises the config as pretty-printed JSON inside the blob', async () => {
      configApiSpy.exportConfig.mockResolvedValue(MOCK_CONFIG);

      const result = await firstValueFrom(service.downloadConfig());
      const blobText = await result.blob.text();
      const parsed = JSON.parse(blobText);

      expect(parsed).toEqual(MOCK_CONFIG);
    });

    it('derives a filename with todays date', async () => {
      configApiSpy.exportConfig.mockResolvedValue(MOCK_CONFIG);

      const today = new Date().toISOString().split('T')[0];
      const result = await firstValueFrom(service.downloadConfig());

      expect(result.filename).toMatch(/^lidar-config-/);
      expect(result.filename).toContain(today);
      expect(result.filename).toMatch(/\.json$/);
    });

    it('propagates HTTP errors from exportConfig', async () => {
      configApiSpy.exportConfig.mockRejectedValue(new Error('HTTP 503'));

      await expect(firstValueFrom(service.downloadConfig())).rejects.toThrow('HTTP 503');
    });
  });
});
