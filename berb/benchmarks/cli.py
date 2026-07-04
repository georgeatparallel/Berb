"""Berb benchmarks CLI."""

from __future__ import annotations

import argparse
import asyncio

from berb.benchmarks import BenchmarkCategory, BenchmarkSuite
from berb.benchmarks.runner import BenchmarkRunner


def benchmarks_cmd(args: argparse.Namespace) -> int:
    """Run benchmarks command."""
    runner = BenchmarkRunner()

    if args.list:
        return cmd_list(args)
    elif args.run:
        return asyncio.run(cmd_run(runner, args.run))
    elif args.suite:
        return asyncio.run(cmd_suite(runner, args))
    else:
        print("Use --list, --run <id>, or --suite")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List available benchmarks."""
    suite = BenchmarkSuite()

    category = None
    if args.category:
        try:
            category = BenchmarkCategory(args.category)
        except ValueError:
            print(f"Invalid category: {args.category}")
            return 1

    benchmarks = suite.list_benchmarks(category=category, difficulty=args.difficulty)

    print(f"\n{'ID':<25} {'Name':<30} {'Category':<20} {'Difficulty':<10}")
    print("-" * 90)

    for b in benchmarks:
        print(f"{b.id:<25} {b.name:<30} {b.category.value:<20} {b.difficulty:<10}")

    print(f"\nTotal: {len(benchmarks)} benchmarks")
    return 0


async def cmd_run(runner: BenchmarkRunner, benchmark_id: str) -> int:
    """Run a single benchmark."""
    print(f"\nRunning benchmark: {benchmark_id}\n")

    result = await runner.run_benchmark(benchmark_id, auto_approve=True)

    if not result:
        print(f"Benchmark '{benchmark_id}' not found")
        return 1

    print(f"\n{'=' * 60}")
    print(f"Benchmark: {result.benchmark_id}")
    print(f"{'=' * 60}")
    print(f"Status:        {result.status}")
    print(f"Success Rate:  {result.success_rate:.0%}")
    print(f"Quality Score: {result.quality_score:.1f}/10")
    print(f"Cost:          ${result.total_cost:.2f}")
    print(f"Duration:      {result.duration_sec:.0f}s")
    print(
        f"Tokens:        {result.total_tokens:,} (in: {result.input_tokens:,}, out: {result.output_tokens:,})"
    )
    print(f"Literature:    {result.literature_count} papers")
    print(f"Repair Cycles: {result.repair_cycles}")
    print(f"{'=' * 60}\n")

    # Save results
    runner.save_results()

    return 0 if result.success_rate > 0.5 else 1


async def cmd_suite(runner: BenchmarkRunner, args: argparse.Namespace) -> int:
    """Run benchmark suite."""
    print("\nRunning benchmark suite")
    if args.category:
        print(f"Category: {args.category}")
    if args.difficulty:
        print(f"Difficulty: {args.difficulty}")
    print()

    await runner.run_suite(
        category=args.category,
        difficulty=args.difficulty,
        auto_approve=True,
    )

    # Print summary
    summary = runner.get_summary()

    print(f"\n{'=' * 60}")
    print("BENCHMARK SUITE SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Run:     {summary.get('total_benchmarks', 0)}")
    print(f"Success Rate:  {summary.get('success_rate', 0):.0%}")
    print(f"Avg Quality:   {summary.get('avg_quality_score', 0):.1f}/10")
    print(f"Avg Cost:      ${summary.get('avg_cost', 0):.2f}")
    print(f"Avg Duration:  {summary.get('avg_duration_sec', 0):.0f}s")
    print(f"Total Cost:    ${summary.get('total_cost', 0):.2f}")
    print(f"{'=' * 60}\n")

    # Generate and save report
    report_path = runner._output_dir / "benchmark_report.md"
    runner.generate_report(report_path)
    runner.save_results()

    print(f"Report saved to: {report_path}")

    return 0


def setup_benchmarks_parser(subparsers: argparse._SubParsersAction) -> None:
    """Setup benchmarks subcommand parser."""
    parser = subparsers.add_parser(
        "benchmarks",
        help="Run competitive benchmarks",
        description="Run standardized benchmarks to measure Berb performance",
    )

    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available benchmarks",
    )

    parser.add_argument(
        "--category",
        "-c",
        type=str,
        choices=[
            "hypothesis-generation",
            "experiment-design",
            "literature-review",
            "code-generation",
            "paper-writing",
            "full-pipeline",
        ],
        help="Filter by category",
    )

    parser.add_argument(
        "--difficulty",
        "-d",
        type=str,
        choices=["easy", "medium", "hard"],
        help="Filter by difficulty",
    )

    parser.add_argument(
        "--run",
        "-r",
        type=str,
        metavar="ID",
        help="Run a specific benchmark by ID",
    )

    parser.add_argument(
        "--suite",
        "-s",
        action="store_true",
        help="Run entire benchmark suite",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output directory for results",
    )

    parser.set_defaults(func=benchmarks_cmd)
