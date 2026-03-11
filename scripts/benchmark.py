#!/usr/bin/env python3
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
MCP Connect Performance Benchmark Script

Compares Python and TypeScript service performance across multiple scenarios:
- Cached requests (cache hit scenario)
- Cold starts (cache miss scenario)
- Concurrent requests (async handling)
- Mixed workload (realistic 70/30 split)

Usage:
    poetry run python scripts/benchmark.py --access-token YOUR_TOKEN
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# ============================================================================
# Test Server Configurations
# ============================================================================

# Test MCP servers for benchmarking
TEST_SERVERS = {
    "filesystem": {
        "serverPath": "npx",
        "args": [
            "-y",
            "@modelcontextprotocol/server-filesystem",
            "/home/taras_spashchenko/temp/tmp",
        ],
        "method": "tools/list",
        "params": {},
    },
    "context7": {
        "serverPath": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        "method": "tools/list",
        "params": {},
        "env": {},
    },
    "time": {
        "serverPath": "uvx",
        "args": ["mcp-server-time"],
        "method": "tools/list",
        "params": {},
    },
}

# ============================================================================
# Utility Functions
# ============================================================================


async def measure_request_latency(
    client: httpx.AsyncClient,
    url: str,
    request_body: dict[str, Any],
    headers: dict[str, str],
) -> tuple[float, bool]:
    """
    Measure single request latency in milliseconds.

    Args:
        client: HTTP client instance
        url: Base service URL
        request_body: JSON request body for /bridge endpoint
        headers: HTTP headers including Authorization

    Returns:
        Tuple of (latency_ms, success)
        - latency_ms: Request latency in milliseconds
        - success: True if request succeeded, False otherwise
    """
    start = time.perf_counter()
    success = False

    try:
        response = await client.post(
            f"{url}/bridge",
            json=request_body,
            headers=headers,
            timeout=60.0,  # Increased for debugging
        )
        response.raise_for_status()
        success = True
    except Exception as e:
        # Log error but return timing anyway for failure analysis
        print(f"Request failed: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()

    end = time.perf_counter()
    latency_ms = (end - start) * 1000
    return latency_ms, success


def calculate_percentiles(latencies: list[float]) -> dict[str, float]:
    """
    Calculate P50, P95, P99 percentiles and other statistics.

    Args:
        latencies: List of latency measurements in milliseconds

    Returns:
        Dictionary with p50, p95, p99, min, max, mean, median
    """
    if not latencies:
        return {
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
        }

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    # Use statistics.quantiles for accurate percentile calculation
    # For P95: we need the 95th percentile, which is quantiles(n=20)[18]
    # For P99: we need the 99th percentile, which is quantiles(n=100)[98]

    try:
        if n >= 100:
            quantiles_100 = statistics.quantiles(sorted_latencies, n=100)
            p99 = quantiles_100[98]
        else:
            # Fallback for small samples
            p99_idx = int(n * 0.99)
            p99 = sorted_latencies[min(p99_idx, n - 1)]

        if n >= 20:
            quantiles_20 = statistics.quantiles(sorted_latencies, n=20)
            p95 = quantiles_20[18]
        else:
            # Fallback for small samples
            p95_idx = int(n * 0.95)
            p95 = sorted_latencies[min(p95_idx, n - 1)]

        quantiles_2 = statistics.quantiles(sorted_latencies, n=2)
        p50 = quantiles_2[0]

    except statistics.StatisticsError:
        # Fallback if quantiles fails (e.g., all values identical)
        p50 = sorted_latencies[n // 2]
        p95 = sorted_latencies[int(n * 0.95)]
        p99 = sorted_latencies[int(n * 0.99)]

    return {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "p99": round(p99, 2),
        "min": round(min(sorted_latencies), 2),
        "max": round(max(sorted_latencies), 2),
        "mean": round(statistics.mean(sorted_latencies), 2),
        "median": round(statistics.median(sorted_latencies), 2),
    }


async def verify_service_health(client: httpx.AsyncClient, url: str, name: str) -> bool:
    """
    Verify service is healthy and responding.

    Args:
        client: HTTP client instance
        url: Base service URL
        name: Service name for logging

    Returns:
        True if healthy, False otherwise
    """
    try:
        response = await client.get(f"{url}/health", timeout=5.0)
        response.raise_for_status()
        print(f"✓ {name} service healthy at {url}")
        return True
    except Exception as e:
        print(f"✗ {name} service health check failed: {e}", file=sys.stderr)
        return False


# ============================================================================
# Benchmark Scenarios
# ============================================================================


async def run_cached_scenario(
    client: httpx.AsyncClient,
    service_url: str,
    access_token: str,
    iterations: int = 1000,
    test_server: str = "filesystem",
) -> dict[str, Any]:
    """
    Scenario 1: Cached requests (same MCP server configuration).

    Sends N sequential requests to the same MCP server to test cache effectiveness.
    Target: P95 < 100ms, cache hit rate > 90%

    Args:
        client: HTTP client instance
        service_url: Base service URL
        access_token: Bearer token
        iterations: Number of requests to send
        test_server: Which test server to use (filesystem or context7)

    Returns:
        Scenario results with percentiles and pass/fail
    """
    print(f"\n🔄 Running cached requests scenario ({iterations} requests, server: {test_server})...")

    # Fixed MCP server configuration for cache hits
    request_body = TEST_SERVERS[test_server].copy()

    headers = {"Authorization": f"Bearer {access_token}"}

    # Warm-up: 50 requests to prime cache and JIT
    print("  Warming up (50 requests)...")
    for _ in range(50):
        await measure_request_latency(client, service_url, request_body, headers)

    # Actual benchmark
    print(f"  Measuring latency ({iterations} requests)...")
    latencies = []
    success_count = 0

    for i in range(iterations):
        if i % 100 == 0 and i > 0:
            print(f"    Progress: {i}/{iterations} requests")

        latency, success = await measure_request_latency(client, service_url, request_body, headers)
        latencies.append(latency)
        if success:
            success_count += 1

    percentiles = calculate_percentiles(latencies)

    # Cache hit rate estimation: requests <50ms are likely cache hits
    cache_hits = len([lat for lat in latencies if lat < 50])
    cache_hit_rate = (cache_hits / iterations) * 100 if iterations > 0 else 0

    # Pass criteria: P95 < 100ms AND cache hit rate > 90%
    pass_result = percentiles["p95"] < 100 and cache_hit_rate > 90

    print(f"  ✓ Completed: P95={percentiles['p95']}ms, cache hit rate={cache_hit_rate:.1f}%")

    return {
        "scenario": "cached_requests",
        "iterations": iterations,
        "success_count": success_count,
        "percentiles": percentiles,
        "cache_hit_rate": round(cache_hit_rate, 2),
        "pass": pass_result,
        "target": "P95 < 100ms, cache hit rate > 90%",
    }


async def run_cold_start_scenario(
    client: httpx.AsyncClient,
    service_url: str,
    access_token: str,
    iterations: int = 100,
    test_server: str = "filesystem",
) -> dict[str, Any]:
    """
    Scenario 2: Cold starts (different MCP server configurations).

    Forces cache misses by varying args to create different cache keys.
    Target: stdio < 2s average

    Args:
        client: HTTP client instance
        service_url: Base service URL
        access_token: Bearer token
        iterations: Number of cold start requests
        test_server: Which test server to use (filesystem or context7)

    Returns:
        Scenario results with percentiles and pass/fail
    """
    print(f"\n❄️  Running cold start scenario ({iterations} requests, server: {test_server})...")

    headers = {"Authorization": f"Bearer {access_token}"}
    latencies = []
    success_count = 0

    for i in range(iterations):
        if i % 10 == 0 and i > 0:
            print(f"    Progress: {i}/{iterations} requests")

        # Vary args to force different cache keys (cache misses)
        request_body = TEST_SERVERS[test_server].copy()

        # For filesystem, vary the path; for others, vary query parameters
        if test_server == "filesystem":
            request_body["args"] = [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                f"/home/taras_spashchenko/temp/tmp/bench-cold-{i}",
            ]
        else:  # context7, time, or other servers
            # Add unique parameter to force cache miss
            request_body["params"] = {"bench_id": f"cold-{i}"}

        latency, success = await measure_request_latency(client, service_url, request_body, headers)
        latencies.append(latency)
        if success:
            success_count += 1

    percentiles = calculate_percentiles(latencies)

    # Pass criteria: mean < 2000ms (2 seconds) for stdio
    pass_result = percentiles["mean"] < 2000

    print(f"  ✓ Completed: mean={percentiles['mean']}ms, P95={percentiles['p95']}ms")

    return {
        "scenario": "cold_starts",
        "iterations": iterations,
        "success_count": success_count,
        "percentiles": percentiles,
        "pass": pass_result,
        "target": "mean < 2000ms (stdio)",
    }


async def run_concurrent_scenario(
    client: httpx.AsyncClient,
    service_url: str,
    access_token: str,
    concurrent_requests: int = 100,
    test_server: str = "filesystem",
) -> dict[str, Any]:
    """
    Scenario 3: Concurrent requests (async handling test).

    Tests async handling with simultaneous requests (70% cached, 30% cold).
    Target: P95 < 200ms, no significant degradation

    Args:
        client: HTTP client instance
        service_url: Base service URL
        access_token: Bearer token
        concurrent_requests: Number of concurrent requests
        test_server: Which test server to use (filesystem or context7)

    Returns:
        Scenario results with throughput and pass/fail
    """
    msg = f"concurrent scenario ({concurrent_requests} requests, server: {test_server})"
    print(f"\n⚡ Running {msg}...")

    headers = {"Authorization": f"Bearer {access_token}"}

    # Pre-warm cache with base configuration
    print("  Warming up cache...")
    warm_body = TEST_SERVERS[test_server].copy()
    for _ in range(20):
        await measure_request_latency(client, service_url, warm_body, headers)

    # Create tasks: 70% cached, 30% cold
    print(f"  Launching {concurrent_requests} concurrent requests...")
    tasks = []

    for i in range(concurrent_requests):
        request_body = TEST_SERVERS[test_server].copy()

        if i % 10 < 7:  # 70% cached - same config
            pass  # Use base config
        else:  # 30% cold - vary config
            if test_server == "filesystem":
                request_body["args"] = [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    f"/home/taras_spashchenko/temp/tmp/bench-concurrent-{i}",
                ]
            else:
                request_body["params"] = {"bench_id": f"concurrent-{i}"}

        task = measure_request_latency(client, service_url, request_body, headers)
        tasks.append(task)

    # Execute concurrently
    start = time.perf_counter()
    results = await asyncio.gather(*tasks)
    end = time.perf_counter()

    # Unpack results
    latencies = [lat for lat, _ in results]
    success_count = sum(1 for _, success in results if success)

    duration_sec = end - start
    throughput = concurrent_requests / duration_sec if duration_sec > 0 else 0

    percentiles = calculate_percentiles(latencies)

    # Pass criteria: P95 < 200ms (allow higher latency for concurrent)
    pass_result = percentiles["p95"] < 200

    print(f"  ✓ Completed: throughput={throughput:.1f} req/s, P95={percentiles['p95']}ms")

    return {
        "scenario": "concurrent_requests",
        "concurrent_count": concurrent_requests,
        "success_count": success_count,
        "duration_sec": round(duration_sec, 2),
        "throughput_req_per_sec": round(throughput, 2),
        "percentiles": percentiles,
        "pass": pass_result,
        "target": "P95 < 200ms, high throughput",
    }


async def run_mixed_workload_scenario(
    client: httpx.AsyncClient,
    service_url: str,
    access_token: str,
    iterations: int = 1000,
    test_server: str = "filesystem",
) -> dict[str, Any]:
    """
    Scenario 4: Mixed workload (realistic production simulation).

    Simulates realistic production: 70% cached (same 10 servers), 30% cold (unique).
    Target: P95 < 150ms, throughput ≥ TypeScript baseline

    Args:
        client: HTTP client instance
        service_url: Base service URL
        access_token: Bearer token
        iterations: Total number of requests
        test_server: Which test server to use (filesystem or context7)

    Returns:
        Scenario results with percentiles and pass/fail
    """
    print(f"\n🔀 Running mixed workload scenario ({iterations} requests, server: {test_server})...")

    headers = {"Authorization": f"Bearer {access_token}"}

    # Pre-warm cache with 10 common server configurations
    print("  Warming up cache with 10 common servers...")
    cached_configs = []
    for i in range(10):
        warm_body = TEST_SERVERS[test_server].copy()
        if test_server == "filesystem":
            warm_body["args"] = [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                f"/home/taras_spashchenko/temp/tmp/bench-cached-{i}",
            ]
        else:
            warm_body["params"] = {"bench_id": f"cached-{i}"}
        cached_configs.append(warm_body)
        await measure_request_latency(client, service_url, warm_body, headers)

    # Run mixed workload
    print(f"  Running mixed workload ({iterations} requests)...")
    latencies = []
    success_count = 0
    cached_count = 0
    cold_count = 0

    for i in range(iterations):
        if i % 100 == 0 and i > 0:
            print(f"    Progress: {i}/{iterations} requests")

        # 70% cached (rotate through 10 servers), 30% cold (unique)
        if i % 10 < 7:  # 70% cached
            request_body = cached_configs[i % len(cached_configs)].copy()
            cached_count += 1
        else:  # 30% cold
            request_body = TEST_SERVERS[test_server].copy()
            if test_server == "filesystem":
                request_body["args"] = [
                    "-y",
                    "@modelcontextprotocol/server-filesystem",
                    f"/home/taras_spashchenko/temp/tmp/bench-cold-{i}",
                ]
            else:
                request_body["params"] = {"bench_id": f"cold-{i}"}
            cold_count += 1

        latency, success = await measure_request_latency(client, service_url, request_body, headers)
        latencies.append(latency)
        if success:
            success_count += 1

    percentiles = calculate_percentiles(latencies)

    # Pass criteria: P95 < 150ms
    pass_result = percentiles["p95"] < 150

    print(f"  ✓ Completed: P95={percentiles['p95']}ms (cached={cached_count}, cold={cold_count})")

    return {
        "scenario": "mixed_workload",
        "iterations": iterations,
        "success_count": success_count,
        "cached_count": cached_count,
        "cold_count": cold_count,
        "percentiles": percentiles,
        "pass": pass_result,
        "target": "P95 < 150ms",
    }


# ============================================================================
# Service Comparison
# ============================================================================


async def run_benchmarks_for_service(
    service_url: str,
    service_name: str,
    access_token: str,
    scenarios: list[str],
    iterations: int,
    test_server: str = "filesystem",
) -> dict[str, Any]:
    """
    Run all benchmark scenarios for a single service.

    Args:
        service_url: Base service URL
        service_name: Service name for logging
        access_token: Bearer token
        scenarios: List of scenario names to run
        iterations: Number of iterations for cached scenario
        test_server: Which test server to use (filesystem or context7)

    Returns:
        Dictionary with all scenario results
    """
    print(f"\n{'=' * 70}")
    print(f"Benchmarking {service_name} at {service_url}")
    print(f"{'=' * 70}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Verify service health
        if not await verify_service_health(client, service_url, service_name):
            return {"error": f"{service_name} service unavailable"}

        results: dict[str, Any] = {
            "service": service_name,
            "url": service_url,
            "test_server": test_server,
            "scenarios": {},
        }

        # Run selected scenarios
        if "cached" in scenarios or "all" in scenarios:
            results["scenarios"]["cached"] = await run_cached_scenario(
                client, service_url, access_token, iterations, test_server
            )

        if "cold" in scenarios or "all" in scenarios:
            results["scenarios"]["cold"] = await run_cold_start_scenario(
                client, service_url, access_token, iterations=100, test_server=test_server
            )

        if "concurrent" in scenarios or "all" in scenarios:
            results["scenarios"]["concurrent"] = await run_concurrent_scenario(
                client, service_url, access_token, concurrent_requests=100, test_server=test_server
            )

        if "mixed" in scenarios or "all" in scenarios:
            results["scenarios"]["mixed"] = await run_mixed_workload_scenario(
                client, service_url, access_token, iterations=iterations, test_server=test_server
            )

        return results


# ============================================================================
# Results Analysis and Output
# ============================================================================


def compare_services(python_results: dict[str, Any], typescript_results: dict[str, Any]) -> dict[str, Any]:
    """
    Compare Python and TypeScript service results.

    Args:
        python_results: Python service benchmark results
        typescript_results: TypeScript service benchmark results

    Returns:
        Comparison data with deltas and pass/fail verdict
    """
    comparison: dict[str, Any] = {"scenarios": {}}

    for scenario_name in python_results.get("scenarios", {}):
        if scenario_name not in typescript_results.get("scenarios", {}):
            continue

        py = python_results["scenarios"][scenario_name]
        ts = typescript_results["scenarios"][scenario_name]

        py_p95 = py["percentiles"]["p95"]
        ts_p95 = ts["percentiles"]["p95"]
        delta_p95 = py_p95 - ts_p95
        delta_pct = (delta_p95 / ts_p95 * 100) if ts_p95 > 0 else 0

        comparison["scenarios"][scenario_name] = {
            "python_p95": py_p95,
            "typescript_p95": ts_p95,
            "delta_ms": round(delta_p95, 2),
            "delta_pct": round(delta_pct, 2),
            "python_pass": py["pass"],
            "typescript_pass": ts["pass"],
        }

    return comparison


def print_summary(
    python_results: dict[str, Any],
    typescript_results: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
) -> None:
    """
    Print benchmark summary to stdout.

    Args:
        python_results: Python service results
        typescript_results: TypeScript service results (optional)
        comparison: Comparison data (optional)
    """
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)

    # Python results
    print(f"\n📊 Python Service ({python_results.get('url', 'N/A')})")
    print("-" * 70)
    for scenario_name, scenario_data in python_results.get("scenarios", {}).items():
        status = "✓ PASS" if scenario_data["pass"] else "✗ FAIL"
        print(f"\n{scenario_name.upper()}: {status}")
        print(f"  P50: {scenario_data['percentiles']['p50']}ms")
        print(f"  P95: {scenario_data['percentiles']['p95']}ms")
        print(f"  P99: {scenario_data['percentiles']['p99']}ms")
        print(f"  Target: {scenario_data['target']}")

        if "cache_hit_rate" in scenario_data:
            print(f"  Cache hit rate: {scenario_data['cache_hit_rate']}%")
        if "throughput_req_per_sec" in scenario_data:
            print(f"  Throughput: {scenario_data['throughput_req_per_sec']} req/s")

    # TypeScript results
    if typescript_results:
        print(f"\n📊 TypeScript Service ({typescript_results.get('url', 'N/A')})")
        print("-" * 70)
        for scenario_name, scenario_data in typescript_results.get("scenarios", {}).items():
            status = "✓ PASS" if scenario_data["pass"] else "✗ FAIL"
            print(f"\n{scenario_name.upper()}: {status}")
            print(f"  P50: {scenario_data['percentiles']['p50']}ms")
            print(f"  P95: {scenario_data['percentiles']['p95']}ms")
            print(f"  P99: {scenario_data['percentiles']['p99']}ms")

            if "cache_hit_rate" in scenario_data:
                print(f"  Cache hit rate: {scenario_data['cache_hit_rate']}%")
            if "throughput_req_per_sec" in scenario_data:
                print(f"  Throughput: {scenario_data['throughput_req_per_sec']} req/s")

    # Comparison
    if comparison:
        print("\n🔍 Python vs TypeScript Comparison")
        print("-" * 70)
        for scenario_name, comp_data in comparison.get("scenarios", {}).items():
            delta_sign = "+" if comp_data["delta_ms"] > 0 else ""
            print(f"\n{scenario_name.upper()}:")
            py_p95 = comp_data["python_p95"]
            ts_p95 = comp_data["typescript_p95"]
            print(f"  Python P95: {py_p95}ms | TypeScript P95: {ts_p95}ms")
            delta_ms = comp_data["delta_ms"]
            delta_pct = comp_data["delta_pct"]
            print(f"  Delta: {delta_sign}{delta_ms}ms ({delta_sign}{delta_pct}%)")

    print("\n" + "=" * 70)


def determine_overall_pass(results: dict[str, Any]) -> bool:
    """
    Determine if all scenarios passed.

    Args:
        results: Benchmark results

    Returns:
        True if all scenarios passed, False otherwise
    """
    for scenario_data in results.get("scenarios", {}).values():
        if not scenario_data.get("pass", False):
            return False
    return True


# ============================================================================
# Test Setup
# ============================================================================


def prepare_filesystem_test_dirs(iterations: int) -> None:
    """
    Create temporary directories needed for filesystem server benchmarks.

    Args:
        iterations: Number of iterations (determines how many dirs to create)
    """
    # Create directories for cold starts, concurrent, and cached scenarios
    dirs_to_create = set()

    # Cold start directories
    for i in range(iterations):
        dirs_to_create.add(f"/home/taras_spashchenko/temp/tmp/bench-cold-{i}")

    # Concurrent directories
    for i in range(100):
        dirs_to_create.add(f"/home/taras_spashchenko/temp/tmp/bench-concurrent-{i}")

    # Cached directories
    for i in range(10):
        dirs_to_create.add(f"/home/taras_spashchenko/temp/tmp/bench-cached-{i}")

    # Create all directories
    for dir_path in dirs_to_create:
        os.makedirs(dir_path, exist_ok=True)

    print(f"✓ Created {len(dirs_to_create)} test directories in /home/taras_spashchenko/temp/tmp/")


# ============================================================================
# Main CLI
# ============================================================================


def main() -> None:
    """Main entry point for benchmark script."""
    parser = argparse.ArgumentParser(
        description="MCP Connect Performance Benchmark - Compare Python and TypeScript services"
    )
    parser.add_argument(
        "--python-url",
        default="http://localhost:3000",
        help="Python service URL (default: http://localhost:3000)",
    )
    parser.add_argument(
        "--typescript-url",
        default="http://localhost:4000",
        help="TypeScript service URL (default: http://localhost:4000)",
    )
    parser.add_argument(
        "--scenario",
        choices=["cached", "cold", "concurrent", "mixed", "all"],
        default="all",
        help="Scenario to run (default: all)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Number of iterations for cached/mixed scenarios (default: 1000)",
    )
    parser.add_argument(
        "--output",
        default="benchmark-results.json",
        help="Output JSON file (default: benchmark-results.json)",
    )
    parser.add_argument(
        "--access-token",
        required=True,
        help="Bearer token for authentication",
    )
    parser.add_argument(
        "--skip-typescript",
        action="store_true",
        help="Skip TypeScript service benchmarking",
    )
    parser.add_argument(
        "--test-server",
        choices=["filesystem", "context7", "time"],
        default="filesystem",
        help="MCP test server to use (default: filesystem)",
    )

    args = parser.parse_args()

    # Determine scenarios to run
    scenarios = [args.scenario] if args.scenario != "all" else ["all"]

    print("=" * 70)
    print("MCP CONNECT PERFORMANCE BENCHMARK")
    print("=" * 70)
    print(f"Scenario(s): {', '.join(scenarios)}")
    print(f"Iterations: {args.iterations}")
    print(f"Test server: {args.test_server}")
    print(f"Output file: {args.output}")
    print("=" * 70)

    # Prepare test environment if using filesystem server
    if args.test_server == "filesystem":
        print("\nPreparing test environment...")
        prepare_filesystem_test_dirs(args.iterations)

    # Run benchmarks
    try:
        # Python service
        python_results = asyncio.run(
            run_benchmarks_for_service(
                args.python_url,
                "Python",
                args.access_token,
                scenarios,
                args.iterations,
                args.test_server,
            )
        )

        # TypeScript service (optional)
        typescript_results = None
        comparison = None

        if not args.skip_typescript:
            typescript_results = asyncio.run(
                run_benchmarks_for_service(
                    args.typescript_url,
                    "TypeScript",
                    args.access_token,
                    scenarios,
                    args.iterations,
                    args.test_server,
                )
            )

            # Compare results
            if "error" not in python_results and "error" not in typescript_results:
                comparison = compare_services(python_results, typescript_results)

        # Print summary
        print_summary(python_results, typescript_results, comparison)

        # Save results
        timestamp = datetime.now().isoformat()
        output_data = {
            "timestamp": timestamp,
            "python": python_results,
            "typescript": typescript_results,
            "comparison": comparison,
        }

        output_path = Path(args.output)
        with output_path.open("w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✓ Results saved to {args.output}")

        # Exit with pass/fail code
        python_pass = determine_overall_pass(python_results)
        if python_pass:
            print("\n✓ ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("\n✗ SOME TESTS FAILED")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n✗ Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Benchmark failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
