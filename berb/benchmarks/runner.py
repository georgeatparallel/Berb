"""Benchmark runner for executing and evaluating benchmarks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from berb.benchmarks import BenchmarkDefinition, BenchmarkResult, BenchmarkSuite
from berb.config import RCConfig

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Execute benchmarks and collect results."""
    
    def __init__(
        self,
        config: RCConfig | None = None,
        output_dir: str = ".berb/benchmarks",
    ) -> None:
        """Initialize benchmark runner.
        
        Args:
            config: Berb configuration
            output_dir: Directory for benchmark results
        """
        self._config = config
        self._output_dir = Path(output_dir)
        self._suite = BenchmarkSuite()
        self._results: list[BenchmarkResult] = []
        
        # Ensure output directory exists
        self._output_dir.mkdir(parents=True, exist_ok=True)
    
    async def run_benchmark(
        self,
        benchmark_id: str,
        auto_approve: bool = True,
    ) -> BenchmarkResult | None:
        """Run a single benchmark.
        
        Args:
            benchmark_id: Benchmark to run
            auto_approve: Skip human approval gates
            
        Returns:
            BenchmarkResult or None if benchmark not found
        """
        benchmark = self._suite.get_benchmark(benchmark_id)
        if not benchmark:
            logger.error(f"Benchmark '{benchmark_id}' not found")
            return None
        
        logger.info(f"Starting benchmark: {benchmark.name}")
        logger.info(f"Topic: {benchmark.topic}")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Run the benchmark pipeline
            result = await self._execute_benchmark(
                benchmark=benchmark,
                auto_approve=auto_approve,
            )
            
            # Validate against success criteria
            result.success_rate = self._evaluate_success(
                result=result,
                criteria=benchmark.success_criteria,
            )
            
            # Check if within budget
            if result.total_cost > benchmark.max_cost:
                logger.warning(
                    f"Benchmark exceeded cost budget: "
                    f"${result.total_cost:.2f} > ${benchmark.max_cost:.2f}"
                )
            
            if result.duration_sec > benchmark.max_duration_sec:
                logger.warning(
                    f"Benchmark exceeded time budget: "
                    f"{result.duration_sec:.0f}s > {benchmark.max_duration_sec:.0f}s"
                )
            
            self._results.append(result)
            logger.info(
                f"Benchmark complete: {benchmark.name} - "
                f"Success: {result.success_rate:.0%}, "
                f"Cost: ${result.total_cost:.2f}, "
                f"Quality: {result.quality_score:.1f}/10"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            # Create failure result
            result = BenchmarkResult(
                benchmark_id=benchmark_id,
                category=benchmark.category.value,
                topic=benchmark.topic,
                status="failed",
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                duration_sec=(datetime.now(timezone.utc) - start_time).total_seconds(),
                total_cost=0.0,
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                quality_score=0.0,
                literature_count=0,
                repair_cycles=0,
                success_rate=0.0,
                metrics={"error": str(e)},
            )
            self._results.append(result)
            return result
    
    async def _execute_benchmark(
        self,
        benchmark: BenchmarkDefinition,
        auto_approve: bool,
    ) -> BenchmarkResult:
        """Execute the benchmark by running the full Berb pipeline.

        Builds a run directory under ``self._output_dir``, overrides the
        research topic from the benchmark definition, runs
        :func:`berb.pipeline.runner.execute_pipeline`, and extracts cost /
        token / quality metrics from the returned :class:`StageResult` list.
        """
        import copy
        import uuid

        from berb.adapters import AdapterBundle
        from berb.pipeline.runner import execute_pipeline
        from berb.pipeline.stages import Stage

        start_time = datetime.now(timezone.utc)

        # Build a per-benchmark run directory so runs don't collide.
        run_id = f"benchmark_{benchmark.id}_{uuid.uuid4().hex[:6]}"
        run_dir = self._output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Clone the config and override the research topic.
        if self._config is None:
            raise RuntimeError(
                "BenchmarkRunner requires a config to run the pipeline. "
                "Pass config=<RCConfig> to BenchmarkRunner()."
            )
        import dataclasses
        bench_config = dataclasses.replace(
            self._config,
            research=dataclasses.replace(
                self._config.research,
                topic=benchmark.topic,
            ),
        )

        adapters = AdapterBundle()

        # Run the pipeline synchronously in the event loop executor so we
        # don't block the async caller while the pipeline is running.
        loop = asyncio.get_event_loop()
        stage_results = await loop.run_in_executor(
            None,
            lambda: execute_pipeline(
                run_dir=run_dir,
                run_id=run_id,
                config=bench_config,
                adapters=adapters,
                auto_approve_gates=auto_approve,
            ),
        )

        end_time = datetime.now(timezone.utc)
        duration_sec = (end_time - start_time).total_seconds()

        # Aggregate metrics from stage results.
        total_cost: float = 0.0
        total_tokens: int = 0
        input_tokens: int = 0
        output_tokens: int = 0
        literature_count: int = 0
        repair_cycles: int = 0
        quality_score: float = 0.0
        failed_stages: int = 0

        for sr in stage_results:
            # StageResult carries a .metrics dict populated by each stage.
            m = getattr(sr, "metrics", {}) or {}
            total_cost += float(m.get("cost_usd", 0.0))
            total_tokens += int(m.get("tokens", 0))
            input_tokens += int(m.get("input_tokens", 0))
            output_tokens += int(m.get("output_tokens", 0))
            literature_count += int(m.get("papers_found", 0))
            repair_cycles += int(m.get("repair_cycles", 0))
            if hasattr(sr, "status") and str(getattr(sr, "status", "")).lower() in ("failed", "error"):
                failed_stages += 1

        # Quality score: fraction of stages that succeeded, scaled to 0–10.
        total_stages = max(len(stage_results), 1)
        quality_score = round(10.0 * (total_stages - failed_stages) / total_stages, 2)

        overall_status = "failed" if failed_stages == total_stages else (
            "partial" if failed_stages > 0 else "success"
        )

        return BenchmarkResult(
            benchmark_id=benchmark.id,
            category=benchmark.category.value,
            topic=benchmark.topic,
            status=overall_status,
            start_time=start_time,
            end_time=end_time,
            duration_sec=duration_sec,
            total_cost=total_cost,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            quality_score=quality_score,
            literature_count=literature_count,
            repair_cycles=repair_cycles,
            success_rate=1.0 if overall_status == "success" else 0.0,
            metrics={
                "benchmark_name": benchmark.name,
                "difficulty": benchmark.difficulty,
                "total_stages": total_stages,
                "failed_stages": failed_stages,
                "run_id": run_id,
            },
        )
    
    def _evaluate_success(
        self,
        result: BenchmarkResult,
        criteria: dict[str, Any],
    ) -> float:
        """Evaluate success rate against criteria.
        
        Args:
            result: Benchmark result
            criteria: Success criteria dictionary
            
        Returns:
            Success rate (0.0 to 1.0)
        """
        if result.status == "failed":
            return 0.0
        
        passed = 0
        total = len(criteria)
        
        for criterion, expected in criteria.items():
            actual = getattr(result, criterion, None)
            
            if actual is None:
                # Check metrics
                actual = result.metrics.get(criterion)
            
            if actual is None:
                continue
            
            # Evaluate based on type
            if isinstance(expected, bool):
                if actual == expected:
                    passed += 1
            elif isinstance(expected, (int, float)):
                if criterion.startswith("min_"):
                    if actual >= expected:
                        passed += 1
                elif criterion.startswith("max_"):
                    if actual <= expected:
                        passed += 1
                else:
                    if abs(actual - expected) < 0.1:
                        passed += 1
            else:
                if actual == expected:
                    passed += 1
        
        return passed / total if total > 0 else 0.0
    
    async def run_suite(
        self,
        category: str | None = None,
        difficulty: str | None = None,
        auto_approve: bool = True,
    ) -> list[BenchmarkResult]:
        """Run entire benchmark suite or filtered subset.
        
        Args:
            category: Filter by category
            difficulty: Filter by difficulty
            auto_approve: Skip human approval gates
            
        Returns:
            List of benchmark results
        """
        benchmarks = self._suite.list_benchmarks(
            category=self._suite._benchmarks[category].category if category and category in self._suite._benchmarks else None,
            difficulty=difficulty,
        )
        
        if category:
            from berb.benchmarks import BenchmarkCategory
            try:
                cat_enum = BenchmarkCategory(category)
                benchmarks = self._suite.list_benchmarks(category=cat_enum)
            except ValueError:
                benchmarks = self._suite.all_benchmarks
        
        logger.info(f"Running {len(benchmarks)} benchmarks")
        
        results = []
        for benchmark in benchmarks:
            result = await self.run_benchmark(benchmark.id, auto_approve)
            if result:
                results.append(result)
        
        return results
    
    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics across all results.
        
        Returns:
            Summary statistics dictionary
        """
        if not self._results:
            return {"error": "No results available"}
        
        total = len(self._results)
        successful = sum(1 for r in self._results if r.status == "success")
        
        avg_cost = sum(r.total_cost for r in self._results) / total
        avg_duration = sum(r.duration_sec for r in self._results) / total
        avg_quality = sum(r.quality_score for r in self._results) / total
        avg_success_rate = sum(r.success_rate for r in self._results) / total
        
        return {
            "total_benchmarks": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_cost": avg_cost,
            "avg_duration_sec": avg_duration,
            "avg_quality_score": avg_quality,
            "avg_success_rate": avg_success_rate,
            "total_cost": sum(r.total_cost for r in self._results),
            "total_duration_sec": sum(r.duration_sec for r in self._results),
        }
    
    def generate_report(self, output_path: str | Path | None = None) -> str:
        """Generate human-readable benchmark report.
        
        Args:
            output_path: Optional file path to save report
            
        Returns:
            Report text
        """
        summary = self.get_summary()
        
        lines = [
            "# Berb Benchmark Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Summary",
            "",
            f"- **Total Benchmarks:** {summary.get('total_benchmarks', 0)}",
            f"- **Success Rate:** {summary.get('success_rate', 0):.0%}",
            f"- **Average Cost:** ${summary.get('avg_cost', 0):.2f}",
            f"- **Average Quality:** {summary.get('avg_quality_score', 0):.1f}/10",
            f"- **Average Success Rate:** {summary.get('avg_success_rate', 0):.0%}",
            "",
            "## Detailed Results",
            "",
        ]
        
        for result in self._results:
            lines.extend([
                f"### {result.benchmark_id}",
                "",
                f"- **Status:** {result.status}",
                f"- **Cost:** ${result.total_cost:.2f}",
                f"- **Duration:** {result.duration_sec:.0f}s",
                f"- **Quality:** {result.quality_score:.1f}/10",
                f"- **Success Rate:** {result.success_rate:.0%}",
                f"- **Literature:** {result.literature_count} papers",
                f"- **Repair Cycles:** {result.repair_cycles}",
                "",
            ])
        
        report = "\n".join(lines)
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Report saved to {output_path}")
        
        return report
    
    def save_results(self, output_path: str | Path | None = None) -> None:
        """Save results to JSON file.
        
        Args:
            output_path: Output file path (default: auto-generated)
        """
        if output_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            output_path = self._output_dir / f"benchmark_results_{timestamp}.json"
        else:
            output_path = Path(output_path)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.get_summary(),
            "results": [r.to_dict() for r in self._results],
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Results saved to {output_path}")
    
    def clear_results(self) -> None:
        """Clear all stored results."""
        self._results.clear()
        logger.info("Benchmark results cleared")
