import {validateWebhookUrl, warnWebhookUrl} from './webhook-config.component';

/**
 * Unit tests for the pure URL validation helpers exported from WebhookConfigComponent.
 *
 * TDD: written before implementation to drive contract.
 */
describe('validateWebhookUrl', () => {
  // ──────────────────────────────────────────────────────────────────────────
  // When webhook is disabled
  // ──────────────────────────────────────────────────────────────────────────

  it('returns null when webhook is disabled (empty URL)', () => {
    expect(validateWebhookUrl('', false)).toBeNull();
  });

  it('returns null when webhook is disabled (any URL)', () => {
    expect(validateWebhookUrl('not-a-url', false)).toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // When webhook is enabled — invalid cases
  // ──────────────────────────────────────────────────────────────────────────

  it('returns error when URL is empty and enabled', () => {
    const result = validateWebhookUrl('', true);
    expect(result).not.toBeNull();
    expect(result).toContain('required');
  });

  it('returns error when URL is whitespace-only and enabled', () => {
    const result = validateWebhookUrl('   ', true);
    expect(result).not.toBeNull();
  });

  it('returns error for invalid URL format', () => {
    const result = validateWebhookUrl('not-a-url', true);
    expect(result).not.toBeNull();
  });

  it('returns error for ftp:// URL', () => {
    const result = validateWebhookUrl('ftp://example.com/hook', true);
    expect(result).not.toBeNull();
    expect(result).toContain('http');
  });

  it('returns error for URL missing protocol', () => {
    const result = validateWebhookUrl('example.com/webhook', true);
    expect(result).not.toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────────────
  // When webhook is enabled — valid cases
  // ──────────────────────────────────────────────────────────────────────────

  it('returns null for valid https URL', () => {
    expect(validateWebhookUrl('https://api.example.com/webhook', true)).toBeNull();
  });

  it('returns null for valid http URL', () => {
    expect(validateWebhookUrl('http://api.example.com/webhook', true)).toBeNull();
  });

  it('returns null for HTTPS URL with path and query', () => {
    expect(
      validateWebhookUrl('https://api.example.com/v1/webhook?token=abc', true),
    ).toBeNull();
  });

  it('trims whitespace before validating', () => {
    expect(validateWebhookUrl('  https://api.example.com/webhook  ', true)).toBeNull();
  });
});

describe('warnWebhookUrl', () => {
  it('returns null when webhook is disabled', () => {
    expect(warnWebhookUrl('http://example.com', false)).toBeNull();
  });

  it('returns null when URL is empty and enabled', () => {
    expect(warnWebhookUrl('', true)).toBeNull();
  });

  it('returns warning message for http URL when enabled', () => {
    const result = warnWebhookUrl('http://api.example.com/webhook', true);
    expect(result).not.toBeNull();
    expect(result!.toLowerCase()).toContain('https');
  });

  it('returns null for https URL', () => {
    expect(warnWebhookUrl('https://api.example.com/webhook', true)).toBeNull();
  });

  it('returns null for invalid URL (error takes precedence)', () => {
    expect(warnWebhookUrl('not-a-url', true)).toBeNull();
  });
});
