"""Performance benchmarks for iCCC components."""

import asyncio
import time
from uuid import uuid4

import pytest

from iccc.models.entities import HookEvent, Task, TaskType
from iccc.observability.collector import EventCollector
from iccc.planning.htn import CompoundTask, HTNPlanner, Method, PrimitiveTask
from iccc.planning.strips import Action, State, STRIPSPlanner
from iccc.queue.redis_queue import RedisTaskQueue


class TestEventCollectionPerformance:
    """Benchmark event collection system."""

    @pytest.mark.asyncio
    async def test_high_volume_event_collection(self):
        """Test handling 10,000 events with batching."""
        collector = EventCollector(
            batch_size=100,
            batch_timeout=0.1,  # Fast flushing for test
            sample_rate=1.0,
            enable_ai_summaries=False,  # Disable for pure throughput test
        )

        collected_batches = []

        def capture_batch(events, summary):
            collected_batches.append(len(events))

        collector.register_flush_callback(capture_batch)

        await collector.start()

        # Generate 10,000 events
        start_time = time.time()
        num_events = 10_000

        for i in range(num_events):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={"agent_id": f"agent-{i % 10}", "tool_name": "Read"},
            )
            await collector.collect(event)

        # Wait for all batches to flush
        await asyncio.sleep(1.0)
        await collector.stop()

        elapsed = time.time() - start_time
        events_per_second = num_events / elapsed

        print(f"\n{'='*60}")
        print(f"Event Collection Performance")
        print(f"{'='*60}")
        print(f"Total events: {num_events:,}")
        print(f"Time elapsed: {elapsed:.2f}s")
        print(f"Throughput: {events_per_second:,.0f} events/sec")
        print(f"Batches created: {len(collected_batches)}")
        print(f"Average batch size: {sum(collected_batches) / len(collected_batches):.1f}")

        # Performance assertions
        assert events_per_second > 5_000, "Should handle at least 5K events/sec"
        assert len(collected_batches) > 0, "Should create batches"

    @pytest.mark.asyncio
    async def test_sampling_overhead(self):
        """Test performance impact of sampling."""
        # Test with sampling disabled (100% rate)
        collector_full = EventCollector(
            batch_size=100,
            sample_rate=1.0,
            enable_ai_summaries=False,
        )
        await collector_full.start()

        start = time.time()
        for _ in range(1000):
            await collector_full.collect(
                HookEvent(
                    session_id=uuid4(),
                    event_type="PreToolUse",
                    data={"agent_id": "test"},
                )
            )
        time_full = time.time() - start
        await collector_full.stop()

        # Test with sampling (10% rate)
        collector_sampled = EventCollector(
            batch_size=100,
            sample_rate=0.1,
            enable_ai_summaries=False,
        )
        await collector_sampled.start()

        start = time.time()
        for _ in range(1000):
            await collector_sampled.collect(
                HookEvent(
                    session_id=uuid4(),
                    event_type="PreToolUse",
                    data={"agent_id": "test"},
                )
            )
        time_sampled = time.time() - start
        await collector_sampled.stop()

        speedup = time_full / time_sampled

        print(f"\n{'='*60}")
        print(f"Sampling Performance Impact")
        print(f"{'='*60}")
        print(f"100% sampling: {time_full:.4f}s")
        print(f"10% sampling: {time_sampled:.4f}s")
        print(f"Speedup: {speedup:.2f}x")

        # Sampling reduces event processing by 90%, but overhead includes
        # async operations, batch management, and sampling check itself
        # A 20% speedup (1.2x) is realistic for async workloads
        assert speedup > 1.2, "Sampling should provide at least 20% speedup"


class TestPlanningPerformance:
    """Benchmark planning algorithms."""

    def test_strips_scalability(self):
        """Test STRIPS planning with increasing problem sizes."""
        planner = STRIPSPlanner()

        results = []

        for num_facts in [5, 10, 20, 30]:
            # Create state with N facts (using strings as STRIPS implementation expects)
            initial_facts = frozenset(f"has_item{i}" for i in range(num_facts))
            initial_state = State(facts=initial_facts)

            goal_facts = set(f"has_item{i}" for i in range(num_facts))
            goal_facts.add("completed_all")
            goal_state = State(facts=frozenset(goal_facts))

            # Create actions
            actions = [
                Action(
                    name="complete",
                    preconditions={f"has_item{i}" for i in range(num_facts)},
                    add_effects={"completed_all"},
                    delete_effects=set(),
                    cost=1.0,
                )
            ]

            # Benchmark
            start = time.time()
            plan = planner.plan(initial_state, goal_state, actions, max_iterations=1000)
            elapsed = time.time() - start

            results.append({"facts": num_facts, "time": elapsed, "found": plan is not None})

        print(f"\n{'='*60}")
        print(f"STRIPS Scalability")
        print(f"{'='*60}")
        for result in results:
            print(
                f"Facts: {result['facts']:2d} | Time: {result['time']:.4f}s | "
                f"Found: {result['found']}"
            )

        # Should complete within reasonable time even for larger problems
        assert results[-1]["time"] < 1.0, "Should solve 30-fact problem in <1s"

    def test_htn_decomposition_performance(self):
        """Test HTN decomposition speed."""
        # Create complex decomposition hierarchy
        methods = [
            Method(
                name="implement_feature",
                task_name="feature",
                preconditions=lambda p: True,
                subtasks=[
                    CompoundTask("design", {}),
                    CompoundTask("implement", {}),
                    CompoundTask("test", {}),
                ],
            ),
            Method(
                name="design_method",
                task_name="design",
                preconditions=lambda p: True,
                subtasks=[
                    PrimitiveTask("api_design", {}, estimated_complexity=3),
                    PrimitiveTask("db_design", {}, estimated_complexity=4),
                ],
            ),
            Method(
                name="implement_method",
                task_name="implement",
                preconditions=lambda p: True,
                subtasks=[
                    PrimitiveTask("backend_code", {}, estimated_complexity=7),
                    PrimitiveTask("frontend_code", {}, estimated_complexity=6),
                ],
            ),
            Method(
                name="test_method",
                task_name="test",
                preconditions=lambda p: True,
                subtasks=[
                    PrimitiveTask("unit_tests", {}, estimated_complexity=4),
                    PrimitiveTask("integration_tests", {}, estimated_complexity=5),
                ],
            ),
        ]

        planner = HTNPlanner(methods=methods)

        # Benchmark decomposition
        num_runs = 1000
        start = time.time()

        for _ in range(num_runs):
            compound = CompoundTask("feature", {})
            primitives = planner.decompose(compound)

        elapsed = time.time() - start
        per_decomposition = elapsed / num_runs * 1000  # Convert to ms

        print(f"\n{'='*60}")
        print(f"HTN Decomposition Performance")
        print(f"{'='*60}")
        print(f"Decompositions: {num_runs:,}")
        print(f"Total time: {elapsed:.3f}s")
        print(f"Per decomposition: {per_decomposition:.2f}ms")

        assert per_decomposition < 10, "Should decompose in <10ms"


@pytest.mark.asyncio
class TestQueuePerformance:
    """Benchmark task queue operations."""

    async def test_queue_throughput(self, redis_client):
        """Test task queue enqueue/dequeue throughput."""
        queue = RedisTaskQueue()
        queue.client = redis_client  # Inject mock client

        # Enqueue benchmark
        num_tasks = 1000
        tasks = [
            Task(
                project_id=uuid4(),
                description=f"Task {i}",
                task_type=TaskType.GENERAL_CODING,
            )
            for i in range(num_tasks)
        ]

        start = time.time()
        for task in tasks:
            await queue.enqueue(task, priority=1)
        enqueue_time = time.time() - start

        # Dequeue benchmark
        start = time.time()
        dequeued_count = 0
        while True:
            task = await queue.dequeue("test-agent")
            if not task:
                break
            dequeued_count += 1
        dequeue_time = time.time() - start

        print(f"\n{'='*60}")
        print(f"Task Queue Performance")
        print(f"{'='*60}")
        print(f"Enqueue: {num_tasks} tasks in {enqueue_time:.3f}s")
        print(f"  Throughput: {num_tasks / enqueue_time:,.0f} tasks/sec")
        print(f"Dequeue: {dequeued_count} tasks in {dequeue_time:.3f}s")
        print(f"  Throughput: {dequeued_count / dequeue_time:,.0f} tasks/sec")

        assert num_tasks / enqueue_time > 500, "Should enqueue >500 tasks/sec"
        assert dequeued_count / dequeue_time > 500, "Should dequeue >500 tasks/sec"
        assert dequeued_count == num_tasks, "All tasks should be dequeued"


@pytest.mark.asyncio
class TestMemoryUsage:
    """Test memory usage under load."""

    async def test_event_collector_memory(self):
        """Ensure event collector doesn't leak memory."""
        import tracemalloc

        tracemalloc.start()

        collector = EventCollector(batch_size=100, sample_rate=1.0)
        await collector.start()

        snapshot1 = tracemalloc.take_snapshot()

        # Generate many events
        for _ in range(10_000):
            event = HookEvent(
                session_id=uuid4(),
                event_type="PreToolUse",
                data={"agent_id": "test", "tool_name": "Read"},
            )
            await collector.collect(event)

        # Wait for batches to flush
        await asyncio.sleep(1.0)

        snapshot2 = tracemalloc.take_snapshot()

        await collector.stop()

        # Compare memory
        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_increase = sum(stat.size_diff for stat in top_stats) / 1024 / 1024  # MB

        print(f"\n{'='*60}")
        print(f"Memory Usage - Event Collector")
        print(f"{'='*60}")
        print(f"Memory increase after 10K events: {total_increase:.2f} MB")

        # Should not leak significant memory (batching should keep it bounded)
        assert total_increase < 50, "Memory increase should be <50MB for 10K events"


def run_benchmarks():
    """Run all benchmarks and generate report."""
    pytest.main(
        [
            __file__,
            "-v",
            "-s",  # Show print output
            "--tb=short",  # Short traceback format
        ]
    )


if __name__ == "__main__":
    run_benchmarks()
