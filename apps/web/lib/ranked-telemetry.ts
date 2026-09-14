export type RankedTelemetryKind =
  | 'insert'
  | 'delete'
  | 'composition'
  | 'paste'
  | 'drop'
  | 'other';

export type RankedChallengeRef = {
  challenge_id: string;
  nonce: string;
};

export type RankedTelemetryEvent = {
  dt_ms: number;
  kind: RankedTelemetryKind;
  trusted: boolean;
  delta: number;
  input_type?: string;
};

export type RecordRankedInput = {
  nowMs: number;
  kind: RankedTelemetryKind;
  trusted: boolean;
  delta: number;
  inputType?: string;
};

export type FlushRankedTelemetry = {
  offset: number;
  fragmentStart: number;
  fragment: string;
  errors: number;
  corrections: number;
  focused: boolean;
  visible: boolean;
};

export type RankedTelemetryBatch = {
  type: 'ranked_telemetry';
  challenge_id: string;
  nonce: string;
  batch_seq: number;
  offset: number;
  fragment_start: number;
  fragment: string;
  errors: number;
  corrections: number;
  focused: boolean;
  visible: boolean;
  events: RankedTelemetryEvent[];
};

export const MAX_RANKED_TELEMETRY_EVENTS = 16;

function requireNonNegativeInteger(value: number, field: string): void {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative integer`);
  }
}

export class RankedTelemetryCollector {
  private readonly challenge: RankedChallengeRef;
  private readonly events: RankedTelemetryEvent[] = [];
  private lastEventAtMs: number | null = null;
  private batchSeq = 0;

  constructor(challenge: RankedChallengeRef) {
    if (!challenge.challenge_id || !challenge.nonce) {
      throw new Error('ranked challenge is incomplete');
    }
    this.challenge = { ...challenge };
  }

  get bufferedEventCount(): number {
    return this.events.length;
  }

  recordInput(input: RecordRankedInput): void {
    if (!Number.isFinite(input.nowMs) || input.nowMs < 0) {
      throw new Error('nowMs must be a non-negative finite number');
    }
    if (!Number.isInteger(input.delta) || input.delta < -32 || input.delta > 32) {
      throw new Error('delta must be an integer between -32 and 32');
    }
    if (input.inputType !== undefined && input.inputType.length > 64) {
      throw new Error('inputType must be at most 64 characters');
    }
    if (this.events.length >= MAX_RANKED_TELEMETRY_EVENTS) {
      throw new Error('telemetry buffer full');
    }

    const elapsed = this.lastEventAtMs === null ? 0 : input.nowMs - this.lastEventAtMs;
    if (elapsed < 0) {
      throw new Error('nowMs must be monotonic');
    }

    const event: RankedTelemetryEvent = {
      dt_ms: Math.min(60_000, Math.round(elapsed)),
      kind: input.kind,
      trusted: input.trusted,
      delta: input.delta,
    };
    if (input.inputType !== undefined) {
      event.input_type = input.inputType;
    }

    this.events.push(event);
    this.lastEventAtMs = input.nowMs;
  }

  flush(input: FlushRankedTelemetry): RankedTelemetryBatch {
    requireNonNegativeInteger(input.offset, 'offset');
    requireNonNegativeInteger(input.fragmentStart, 'fragmentStart');
    requireNonNegativeInteger(input.errors, 'errors');
    requireNonNegativeInteger(input.corrections, 'corrections');

    if (input.fragmentStart > input.offset) {
      throw new Error('fragmentStart cannot exceed offset');
    }
    if (input.fragment.length !== input.offset - input.fragmentStart) {
      throw new Error('fragment length must match offset range');
    }
    if (input.fragment.length > 256) {
      throw new Error('fragment must be at most 256 characters');
    }

    this.batchSeq += 1;
    const batch: RankedTelemetryBatch = {
      type: 'ranked_telemetry',
      challenge_id: this.challenge.challenge_id,
      nonce: this.challenge.nonce,
      batch_seq: this.batchSeq,
      offset: input.offset,
      fragment_start: input.fragmentStart,
      fragment: input.fragment,
      errors: input.errors,
      corrections: input.corrections,
      focused: input.focused,
      visible: input.visible,
      events: this.events.map((event) => ({ ...event })),
    };

    this.events.length = 0;
    return batch;
  }
}
