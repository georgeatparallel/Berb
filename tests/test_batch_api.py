"""Unit tests for batch API."""

import asyncio
import time

import pytest

from berb.llm.batch_api import (
    BatchClient,
    BatchPipelineIntegration,
    BatchPriority,
    BatchRequest,
    BatchStatus,
    is_batch_compatible,
)


class TestBatchRequest:
    """Test BatchRequest dataclass."""

    def test_create_request(self):
        """Test creating a batch request."""
        req = BatchRequest(
            custom_id="req_1",
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=100,
        )

        assert req.custom_id == "req_1"
        assert req.model == "gpt-4o"
        assert req.max_tokens == 100


class TestBatchClient:
    """Test BatchClient class."""

    @pytest.mark.asyncio
    async def test_submit_batch(self):
        """Test submitting a batch job."""
        client = BatchClient(api_key="test_key")

        requests = [
            BatchRequest(
                custom_id=f"req_{i}",
                model="gpt-4o",
                messages=[{"role": "user", "content": f"test {i}"}],
            )
            for i in range(5)
        ]

        job = await client.submit_batch(requests)

        assert job.id.startswith("batch_")
        assert job.status == BatchStatus.PENDING
        assert job.total_requests == 5

    @pytest.mark.asyncio
    async def test_get_job_status(self):
        """Test getting job status."""
        client = BatchClient(api_key="test_key")

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        ]

        job = await client.submit_batch(requests)

        # Get status immediately (should be pending)
        status = await client.get_job_status(job.id)
        assert status.status == BatchStatus.PENDING

    @pytest.mark.asyncio
    async def test_poll_until_complete(self):
        """Test polling until completion."""
        client = BatchClient(api_key="test_key")

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        ]

        job = await client.submit_batch(requests)

        # Simulate time passing for status progression
        job.created_at = asyncio.get_event_loop().time() - 7200  # 2 hours ago

        result = await client.poll_until_complete(job.id, poll_interval=1)

        assert result.status == BatchStatus.COMPLETED
        assert result.completed_requests == result.total_requests

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """Test cancelling a job."""
        client = BatchClient(api_key="test_key")

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        ]

        job = await client.submit_batch(requests)

        # Cancel immediately (while pending)
        success = await client.cancel_job(job.id)

        assert success is True
        assert job.status == BatchStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_job(self):
        """Test cancelling already completed job."""
        client = BatchClient(api_key="test_key")

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "test"}],
            )
        ]

        job = await client.submit_batch(requests)
        job.status = BatchStatus.COMPLETED

        success = await client.cancel_job(job.id)

        assert success is False

    def test_get_discount_rate(self):
        """Test discount rate calculation."""
        client = BatchClient(api_key="test_key", priority=BatchPriority.LOW)

        assert client.get_discount_rate() == 0.50
        assert client.get_discount_rate(BatchPriority.MEDIUM) == 0.25
        assert client.get_discount_rate(BatchPriority.HIGH) == 0.0

    def test_estimate_savings(self):
        """Test cost savings estimation."""
        client = BatchClient(api_key="test_key", priority=BatchPriority.LOW)

        savings = client.estimate_savings(regular_cost=100.0)

        assert savings["regular_cost"] == 100.0
        assert savings["batch_cost"] == 50.0  # 50% discount
        assert savings["savings"] == 50.0
        assert savings["discount_rate"] == 0.50

    def test_get_stats(self):
        """Test getting statistics."""
        client = BatchClient(api_key="test_key")

        stats = client.get_stats()

        assert "total_jobs" in stats
        assert "completed_jobs" in stats
        assert "pending_jobs" in stats
        assert "failed_jobs" in stats


class TestBatchPriority:
    """Test batch priority levels."""

    def test_priority_discount_rates(self):
        """Test discount rates for all priority levels."""
        assert BatchClient.DISCOUNT_RATES[BatchPriority.LOW] == 0.50
        assert BatchClient.DISCOUNT_RATES[BatchPriority.MEDIUM] == 0.25
        assert BatchClient.DISCOUNT_RATES[BatchPriority.HIGH] == 0.0

    def test_priority_completion_windows(self):
        """Test completion windows for all priority levels."""
        assert BatchClient.COMPLETION_WINDOWS[BatchPriority.LOW] == "24h"
        assert BatchClient.COMPLETION_WINDOWS[BatchPriority.MEDIUM] == "12h"
        assert BatchClient.COMPLETION_WINDOWS[BatchPriority.HIGH] == "1h"


class TestBatchCompatibility:
    """Test batch compatibility checking."""

    def test_batch_compatible_stages(self):
        """Test stages compatible with batch processing."""
        assert is_batch_compatible("LITERATURE_SCREEN") is True
        assert is_batch_compatible("PEER_REVIEW") is True
        assert is_batch_compatible("QUALITY_GATE") is True
        assert is_batch_compatible("CITATION_VERIFY") is True

    def test_batch_incompatible_stages(self):
        """Test stages not compatible with batch processing."""
        assert is_batch_compatible("CODE_GENERATION") is False
        assert is_batch_compatible("HYPOTHESIS_GEN") is False
        assert is_batch_compatible("EXPERIMENT_RUN") is False


class TestBatchPipelineIntegration:
    """Test batch pipeline integration."""

    @pytest.mark.asyncio
    async def test_submit_stage_batch(self):
        """Test submitting batch for a stage."""
        batch_client = BatchClient(api_key="test_key")
        integration = BatchPipelineIntegration(batch_client)

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "review"}],
            )
        ]

        job_id = await integration.submit_stage_batch("PEER_REVIEW", requests)

        assert job_id.startswith("batch_")
        assert "PEER_REVIEW" in integration._pending_batches

    @pytest.mark.asyncio
    async def test_wait_for_stage_batch(self):
        """Test waiting for stage batch."""
        batch_client = BatchClient(api_key="test_key")
        integration = BatchPipelineIntegration(batch_client)

        requests = [
            BatchRequest(
                custom_id="req_1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "review"}],
            )
        ]

        job = await integration.submit_stage_batch("PEER_REVIEW", requests)

        # Manually complete the job (skip polling)
        batch_job = batch_client._jobs[job]
        batch_job.status = BatchStatus.COMPLETED
        batch_job.completed_requests = 1
        batch_job.completed_at = time.time()

        # Mock poll_until_complete to return immediately
        original_poll = batch_client.poll_until_complete

        async def mock_poll(job_id, **kwargs):
            return batch_client._jobs[job_id]

        batch_client.poll_until_complete = mock_poll

        result = await integration.wait_for_stage_batch("PEER_REVIEW")

        # Restore original
        batch_client.poll_until_complete = original_poll

        assert result.status == BatchStatus.COMPLETED
        assert "PEER_REVIEW" not in integration._pending_batches

    @pytest.mark.asyncio
    async def test_wait_for_nonexistent_batch(self):
        """Test waiting for nonexistent batch."""
        batch_client = BatchClient(api_key="test_key")
        integration = BatchPipelineIntegration(batch_client)

        with pytest.raises(ValueError, match="No pending batch"):
            await integration.wait_for_stage_batch("NONEXISTENT_STAGE")
