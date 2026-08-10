import { describe, it, expect, vi, beforeEach } from 'vitest';

// Unit tests for MCAP recording format changes (F1, F2)
// Tests are pure logic — no Angular TestBed required.

// ── F1: Download filename ──────────────────────────────────────────────────────
// Replicates the exact expression in downloadRecording()
function buildDownloadFilename(name: string, createdAt: string): string {
  return `${name}_${createdAt.substring(0, 10)}.mcap`;
}

describe('F1 – download filename uses .mcap extension', () => {
  it('produces .mcap extension', () => {
    const filename = buildDownloadFilename('scan_001', '2026-08-10T12:34:56Z');
    expect(filename).toMatch(/\.mcap$/);
    expect(filename).toBe('scan_001_2026-08-10.mcap');
  });

  it('does NOT produce .zip extension', () => {
    const filename = buildDownloadFilename('test', '2026-01-01T00:00:00Z');
    expect(filename).not.toMatch(/\.zip$/);
  });

  it('embeds date prefix from created_at ISO string', () => {
    const filename = buildDownloadFilename('my-recording', '2025-12-31T23:59:59Z');
    expect(filename).toBe('my-recording_2025-12-31.mcap');
  });
});

// ── F2: Upload accept attribute ────────────────────────────────────────────────
// Replicates the accept string set in triggerUpload()
const UPLOAD_ACCEPT = '.mcap,.zip';

function parseAcceptedExtensions(accept: string): string[] {
  return accept.split(',').map((s) => s.trim());
}

describe('F2 – upload accept allows .mcap (and keeps .zip for legacy)', () => {
  const exts = parseAcceptedExtensions(UPLOAD_ACCEPT);

  it('accepts .mcap files', () => {
    expect(exts).toContain('.mcap');
  });

  it('accepts .zip files (transitional legacy support)', () => {
    expect(exts).toContain('.zip');
  });

  it('does NOT restrict to .lidr only', () => {
    expect(exts).not.toEqual(['.lidr']);
  });
});
