import { describe, expect, it } from 'vitest';

import { RankedTelemetryCollector } from './ranked-telemetry';

const challenge = {
  challenge_id: 'challenge-1',
  nonce: 'nonce-1',
};

describe('RankedTelemetryCollector', () => {
  it('records trusted race input timing and emits a challenge-bound batch', () => {
    const collector = new RankedTelemetryCollector(challenge);

    collector.recordInput({ nowMs: 1000, kind: 'insert', trusted: true, delta: 1, inputType: 'insertText' });
    collector.recordInput({ nowMs: 1090, kind: 'insert', trusted: true, delta: 1, inputType: 'insertText' });

    const batch = collector.flush({
      offset: 2,
      fragmentStart: 0,
      fragment: 'ко',
      errors: 0,
      corrections: 0,
      focused: true,
      visible: true,
    });

    expect(batch.challenge_id).toBe('challenge-1');
    expect(batch.nonce).toBe('nonce-1');
    expect(batch.batch_seq).toBe(1);
    expect(batch.events).toEqual([
      { dt_ms: 0, kind: 'insert', trusted: true, delta: 1, input_type: 'insertText' },
      { dt_ms: 90, kind: 'insert', trusted: true, delta: 1, input_type: 'insertText' },
    ]);
  });

  it('records correction and paste provenance without recording arbitrary key names', () => {
    const collector = new RankedTelemetryCollector(challenge);

    collector.recordInput({ nowMs: 100, kind: 'delete', trusted: true, delta: -1, inputType: 'deleteContentBackward' });
    collector.recordInput({ nowMs: 140, kind: 'paste', trusted: true, delta: 4, inputType: 'insertFromPaste' });

    const batch = collector.flush({
      offset: 0,
      fragmentStart: 0,
      fragment: '',
      errors: 1,
      corrections: 1,
      focused: true,
      visible: true,
    });

    expect(batch.events.map((event) => event.kind)).toEqual(['delete', 'paste']);
    expect(batch.events[0]).not.toHaveProperty('key');
  });

  it('copies focus and visibility state only when the race input flushes', () => {
    const collector = new RankedTelemetryCollector(challenge);
    collector.recordInput({ nowMs: 100, kind: 'insert', trusted: true, delta: 1 });

    const batch = collector.flush({
      offset: 1,
      fragmentStart: 0,
      fragment: 'к',
      errors: 0,
      corrections: 0,
      focused: false,
      visible: false,
    });

    expect(batch.focused).toBe(false);
    expect(batch.visible).toBe(false);
  });

  it('increments sequence and clears only the flushed event buffer', () => {
    const collector = new RankedTelemetryCollector(challenge);
    collector.recordInput({ nowMs: 100, kind: 'insert', trusted: true, delta: 1 });

    const first = collector.flush({
      offset: 1,
      fragmentStart: 0,
      fragment: 'к',
      errors: 0,
      corrections: 0,
      focused: true,
      visible: true,
    });
    collector.recordInput({ nowMs: 220, kind: 'insert', trusted: true, delta: 1 });
    const second = collector.flush({
      offset: 2,
      fragmentStart: 1,
      fragment: 'о',
      errors: 0,
      corrections: 0,
      focused: true,
      visible: true,
    });

    expect(first.batch_seq).toBe(1);
    expect(second.batch_seq).toBe(2);
    expect(second.events).toHaveLength(1);
    expect(second.events[0].dt_ms).toBe(120);
  });

  it('refuses a seventeenth buffered event instead of silently losing evidence', () => {
    const collector = new RankedTelemetryCollector(challenge);

    for (let index = 0; index < 16; index += 1) {
      collector.recordInput({ nowMs: 100 + index * 10, kind: 'insert', trusted: true, delta: 1 });
    }

    expect(() => {
      collector.recordInput({ nowMs: 300, kind: 'insert', trusted: true, delta: 1 });
    }).toThrow('telemetry buffer full');
    expect(collector.bufferedEventCount).toBe(16);
  });

  it('validates event bounds before buffering malformed data', () => {
    const collector = new RankedTelemetryCollector(challenge);

    expect(() => collector.recordInput({ nowMs: 100, kind: 'insert', trusted: true, delta: 100 })).toThrow('delta');
    expect(() => collector.recordInput({ nowMs: -1, kind: 'insert', trusted: true, delta: 1 })).toThrow('nowMs');
    expect(collector.bufferedEventCount).toBe(0);
  });
});
