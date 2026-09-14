from __future__ import annotations

import secrets

# Original short MVP phrases. Keeping the first catalog entries compact also makes
# the realtime/anti-cheat integration easy to exercise end-to-end; longer texts
# are handled by sequential telemetry batches using the same protocol.
RANKED_TEXTS: tuple[str, ...] = (
    'быстрый набор',
    'точность важна',
    'печатай честно',
    'держи темп',
)


def choose_ranked_text() -> str:
    return secrets.choice(RANKED_TEXTS)
