"""
Proof aggregation for local orchestrator state.
"""

import asyncio
import hashlib
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from .config import OrchestratorSettings

logger = logging.getLogger(__name__)


def sha256(data: bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def compute_merkle_root(leaves: List[str]) -> str:
    if not leaves:
        return "0" * 64

    hashes = [leaf.lower().strip() for leaf in leaves]
    while len(hashes) & (len(hashes) - 1) != 0:
        hashes.append(hashes[-1])

    while len(hashes) > 1:
        next_level = []
        for index in range(0, len(hashes), 2):
            combined = bytes.fromhex(hashes[index]) + bytes.fromhex(hashes[index + 1])
            next_level.append(hashlib.sha256(combined).hexdigest())
        hashes = next_level

    return hashes[0]


class ProofAggregator:
    """Manages local proof aggregation and epoch summaries."""

    def __init__(self, settings: OrchestratorSettings):
        self.settings = settings
        self.pending_proofs: List[Any] = []
        self.epoch_proofs: Dict[int, List[Any]] = defaultdict(list)
        self.epoch_summaries: Dict[int, Any] = {}
        self.aggregated_batches: List[Dict[str, Any]] = []

    async def persist_bandwidth_proof(self, proof, current_epoch: int, subnet_core_client) -> None:
        """BeamCore owns canonical proof persistence; keep the hook as a no-op."""
        return None

    def get_publish_health(self) -> Dict[str, Any]:
        return {
            "success_count": 0,
            "failure_count": 0,
            "retry_queue_size": 0,
            "success_rate": 1.0,
        }

    async def proof_aggregation_loop(self, running_flag, subnet_core_client_ref=None) -> None:
        while running_flag():
            try:
                await asyncio.sleep(self.settings.proof_aggregation_interval)
                if len(self.pending_proofs) >= self.settings.proof_batch_size:
                    await self._aggregate_proofs()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in proof aggregation: {exc}")

    async def _aggregate_proofs(self) -> None:
        if not self.pending_proofs:
            return

        batch = self.pending_proofs[: self.settings.proof_batch_size]
        self.pending_proofs = self.pending_proofs[self.settings.proof_batch_size :]

        leaves = []
        for proof in batch:
            leaf_data = (
                proof.task_id.encode("utf-8")
                + proof.worker_id.encode("utf-8")
                + proof.bytes_relayed.to_bytes(8, "big")
                + int(proof.bandwidth_mbps * 1000).to_bytes(8, "big")
                + int(getattr(proof, "start_time_us", 0)).to_bytes(8, "big")
            )
            leaves.append(sha256(leaf_data))

        merkle_root = compute_merkle_root(leaves)
        self.aggregated_batches.append(
            {
                "epoch": 0,
                "batch_size": len(batch),
                "merkle_root": merkle_root,
                "timestamp": time.time(),
                "total_bytes": sum(proof.bytes_relayed for proof in batch),
                "avg_bandwidth": sum(proof.bandwidth_mbps for proof in batch) / len(batch),
            }
        )

    def build_epoch_summary(self, current_epoch: int, epoch_start_time: datetime = None):
        from .orchestrator import EpochSummary

        proofs = self.epoch_proofs.get(current_epoch, [])
        total_bytes = sum(proof.bytes_relayed for proof in proofs)
        total_bandwidth_seconds = sum(
            proof.bytes_relayed * 8 / 1_000_000 / proof.bandwidth_mbps
            for proof in proofs
            if proof.bandwidth_mbps > 0
        )

        contributions = defaultdict(int)
        for proof in proofs:
            contributions[proof.worker_id] += proof.bytes_relayed

        active_workers = len(set(proof.worker_id for proof in proofs))
        avg_bandwidth = (
            sum(proof.bandwidth_mbps for proof in proofs) / len(proofs) if proofs else 0.0
        )
        avg_latency = sum(proof.duration_ms for proof in proofs) / len(proofs) if proofs else 0.0

        return EpochSummary(
            epoch=current_epoch,
            start_time=epoch_start_time or datetime.utcnow(),
            end_time=datetime.utcnow(),
            total_tasks=len(proofs),
            successful_tasks=len(proofs),
            total_bytes_relayed=total_bytes,
            total_bandwidth_seconds=total_bandwidth_seconds,
            active_workers=active_workers,
            worker_contributions=dict(contributions),
            proof_count=len(proofs),
            avg_bandwidth_mbps=avg_bandwidth,
            avg_latency_ms=avg_latency,
            success_rate=1.0 if proofs else 0.0,
        )
