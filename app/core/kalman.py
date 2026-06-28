from __future__ import annotations

import numpy as np


def smooth_profile_kalman(values: np.ndarray, q: float = 0.1, r: float = 1.0) -> np.ndarray:
    if values.size == 0:
        return values.astype(float)

    q = float(max(q, 1e-9))
    r = float(max(r, 1e-9))

    x = float(values[0])
    p = 1.0
    out = np.empty(values.shape[0], dtype=float)

    for i, z in enumerate(values):
        p = p + q
        k = p / (p + r)
        x = x + k * (float(z) - x)
        p = (1.0 - k) * p
        out[i] = x

    return out
