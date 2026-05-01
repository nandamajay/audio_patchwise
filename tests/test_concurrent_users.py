"""
Concurrent user load test - validates thread safety.
Run: python tests/test_concurrent_users.py --users 10
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx

BASE_URL = "http://localhost:7000"

SAMPLE_PATCH = """
diff --git a/sound/soc/codecs/rt5682.c b/sound/soc/codecs/rt5682.c
index abc123..def456 100644
--- a/sound/soc/codecs/rt5682.c
+++ b/sound/soc/codecs/rt5682.c
@@ -100,6 +100,8 @@ static int rt5682_probe(struct snd_soc_component *component)
+    if (!component)
+        return -EINVAL;
     rt5682->component = component;
"""


async def _create_session(client: httpx.AsyncClient) -> str:
    legacy_payload = {
        "kernel_version": "6.8",
        "subsystem": "audio",
        "source_path": "sound/soc/",
        "llm_model": "gpt-4o",
        "max_rounds": 2,
    }

    response = await client.post(f"{BASE_URL}/api/session/start", json=legacy_payload)
    response.raise_for_status()
    session_id = response.json()["session_id"]

    submit_response = await client.post(
        f"{BASE_URL}/api/patch/submit",
        json={
            "session_id": session_id,
            "patch_input": SAMPLE_PATCH,
        },
    )
    submit_response.raise_for_status()
    return session_id


async def simulate_user(user_id: int, client: httpx.AsyncClient) -> dict:
    """Simulate a single user submitting a patch and reading session state."""
    start = time.time()
    try:
        session_id = await _create_session(client)

        session_response = await client.get(f"{BASE_URL}/api/sessions/{session_id}")
        if session_response.status_code != 200:
            raise RuntimeError(f"Session fetch failed: {session_response.status_code}")

        duration = time.time() - start
        return {
            "user_id": user_id,
            "session_id": session_id,
            "status": "ok",
            "duration": duration,
        }
    except Exception as exc:
        return {
            "user_id": user_id,
            "status": "error",
            "error": str(exc),
        }


async def run_load_test(num_users: int):
    print(f"\nPatchWise Concurrent Load Test - {num_users} simultaneous users")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [simulate_user(i, client) for i in range(num_users)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    ok = sum(1 for result in results if isinstance(result, dict) and result.get("status") == "ok")
    errors = sum(1 for result in results if isinstance(result, dict) and result.get("status") == "error")
    durations = [
        result["duration"]
        for result in results
        if isinstance(result, dict) and "duration" in result
    ]

    print(f"\nSuccessful: {ok}/{num_users}")
    print(f"Errors: {errors}/{num_users}")

    if durations:
        print(f"Avg response time: {sum(durations) / len(durations):.2f}s")
        print(f"Max response time: {max(durations):.2f}s")

    for result in results:
        if isinstance(result, dict) and result.get("status") == "error":
            print(f"  User {result['user_id']}: {result.get('error')}")

    if errors == 0:
        print("\nALL PASSED - Thread safety validated")
    else:
        print(f"\n{errors} failures - check logs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run_load_test(args.users))
