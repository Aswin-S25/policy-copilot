"""Fire concurrent /talk requests at a running API; report status and latency.

    python -m eval.load_probe --concurrency 6                 # distinct users
    python -m eval.load_probe --concurrency 5 --same-user     # one user
"""
import argparse
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.security import create_access_token

QUESTION = "How many days of annual leave do employees get?"


def one(url: str, token: str) -> tuple[int, float]:
    start = time.perf_counter()
    response = httpx.post(
        f"{url}/talk",
        json={"question": QUESTION},
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
    )
    return response.status_code, time.perf_counter() - start


def main(url: str, concurrency: int, same_user: bool) -> None:
    tokens = [
        create_access_token("load-0" if same_user else f"load-{i}", ["employee"])
        for i in range(concurrency)
    ]

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda t: one(url, t), tokens))

    for status, seconds in sorted(results, key=lambda r: r[1]):
        print(f"  HTTP {status}  {seconds:6.1f} s")

    by_status = defaultdict(list)
    for status, seconds in results:
        by_status[status].append(seconds)
    print()
    for status, times in sorted(by_status.items()):
        print(f"HTTP {status}: n={len(times)}  median={statistics.median(times):.1f}s  "
              f"max={max(times):.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--same-user", action="store_true")
    args = parser.parse_args()
    main(args.url, args.concurrency, args.same_user)
