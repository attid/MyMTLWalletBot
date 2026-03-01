from __future__ import annotations

import time
from statistics import mean

from argon2.low_level import Type, hash_secret_raw


CASES: tuple[tuple[int, int, int], ...] = (
    (64 * 1024, 2, 1),
    (64 * 1024, 3, 1),
    (96 * 1024, 2, 1),
    (96 * 1024, 3, 1),
    (128 * 1024, 2, 1),
    (128 * 1024, 3, 1),
)


def benchmark_case(
    memory_kib: int, time_cost: int, parallelism: int
) -> tuple[float, float, float]:
    password = b"benchmark-password"
    salt = b"0123456789abcdef"
    samples_ms: list[float] = []
    for _ in range(7):
        t0 = time.perf_counter()
        hash_secret_raw(
            secret=password,
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_kib,
            parallelism=parallelism,
            hash_len=32,
            type=Type.ID,
        )
        samples_ms.append((time.perf_counter() - t0) * 1000)
    return mean(samples_ms), min(samples_ms), max(samples_ms)


def main() -> int:
    print("Argon2id benchmark (run this on target server)")
    for memory_kib, time_cost, parallelism in CASES:
        avg_ms, min_ms, max_ms = benchmark_case(memory_kib, time_cost, parallelism)
        print(
            f"m={memory_kib // 1024:>3}MiB t={time_cost} p={parallelism} "
            f"-> avg={avg_ms:7.1f}ms min={min_ms:7.1f}ms max={max_ms:7.1f}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
