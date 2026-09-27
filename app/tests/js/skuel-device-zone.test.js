/**
 * "Use this device's time zone" pins for static/js/skuel.js (SKUEL.useDeviceZone).
 *
 * The Settings button selects the browser's own IANA zone in the zone list
 * when the list carries it, and says so in the note; a zone the list lacks,
 * or a browser that reports none, is named in the note and nothing changes.
 * The form's save keeps the choice — the button never submits.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadSkuel } from './helpers/load-skuel.js';

function mountZoneList() {
  document.body.innerHTML = `
    <select id="timezone" name="timezone">
      <option value="" selected>SKUEL default (America/Vancouver)</option>
      <option value="America/Vancouver">America/Vancouver</option>
      <option value="Asia/Bangkok">Asia/Bangkok</option>
    </select>
    <p id="timezone-device-note"></p>
  `;
  return {
    select: document.getElementById('timezone'),
    note: document.getElementById('timezone-device-note'),
  };
}

function deviceZone(timeZone) {
  vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(() => ({
    resolvedOptions: () => ({ timeZone }),
  }));
}

beforeEach(() => {
  loadSkuel();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SKUEL.useDeviceZone', () => {
  it("selects the device's zone when the list carries it", () => {
    const { select, note } = mountZoneList();
    deviceZone('Asia/Bangkok');
    const changes = vi.fn();
    select.addEventListener('change', changes);

    expect(window.SKUEL.useDeviceZone('timezone', 'timezone-device-note')).toBe('Asia/Bangkok');

    expect(select.value).toBe('Asia/Bangkok');
    expect(note.textContent).toBe('Selected Asia/Bangkok. Save to keep it.');
    expect(changes).toHaveBeenCalledTimes(1);
  });

  it('names a zone the list lacks and leaves the choice alone', () => {
    const { select, note } = mountZoneList();
    deviceZone('Mars/Olympus');

    expect(window.SKUEL.useDeviceZone('timezone', 'timezone-device-note')).toBeNull();

    expect(select.value).toBe('');
    expect(note.textContent).toBe('This device reports Mars/Olympus, which is not in the list.');
  });

  it('never picks the SKUEL default for a browser that reports no zone', () => {
    const { select, note } = mountZoneList();
    select.value = 'America/Vancouver';
    deviceZone(undefined);

    expect(window.SKUEL.useDeviceZone('timezone', 'timezone-device-note')).toBeNull();

    expect(select.value).toBe('America/Vancouver');
    expect(note.textContent).toBe('This browser does not report its time zone.');
  });

  it('does nothing without its list', () => {
    document.body.innerHTML = '';
    deviceZone('Asia/Bangkok');
    expect(window.SKUEL.useDeviceZone('timezone', 'timezone-device-note')).toBeNull();
  });
});
