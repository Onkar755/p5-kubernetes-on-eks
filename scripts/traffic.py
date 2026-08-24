import argparse
import concurrent.futures
import time
import urllib.request


def send_request(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/items/123")
    parser.add_argument("--rps", type=float, default=50)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()

    interval = 1 / args.rps
    start = time.monotonic()
    deadline = start + args.duration
    next_request = start

    futures = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:

        while time.monotonic() < deadline:
            now = time.monotonic()

            if now >= next_request:
                futures.append(executor.submit(send_request, args.url))
                next_request += interval
            else:
                time.sleep(next_request - now)

    elapsed = time.monotonic() - start

    succeeded = sum(f.result() for f in futures)
    failed = len(futures) - succeeded

    print(
        f"sent={len(futures)} "
        f"succeeded={succeeded} "
        f"failed={failed} "
        f"elapsed={elapsed:.2f}s "
        f"actual_rps={len(futures) / args.duration:.2f} "
        f"target_rps={args.rps}"
    )


if __name__ == "__main__":
    main()