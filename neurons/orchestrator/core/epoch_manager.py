"""
Epoch lifecycle helpers for the orchestrator.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from .config import OrchestratorSettings

logger = logging.getLogger(__name__)


class EpochManager:
    """Manages epoch lifecycle helpers for the orchestrator."""

    def __init__(self, settings: OrchestratorSettings):
        self.settings = settings

    async def epoch_management_loop(
        self,
        running_flag,
        current_epoch_ref,
        epoch_start_time_ref,
        advance_epoch_fn,
        process_payment_retry_fn,
    ) -> None:
        """Background loop for managing epochs."""
        epoch_duration = timedelta(minutes=5)

        while running_flag():
            try:
                await asyncio.sleep(60)
                await process_payment_retry_fn()

                if datetime.utcnow() - epoch_start_time_ref() >= epoch_duration:
                    await advance_epoch_fn()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in epoch management: {exc}")

    async def generate_payment_proofs(
        self,
        epoch: int,
        workers_values,
        hotkey: str,
        our_uid,
        wallet,
    ) -> Optional[str]:
        """
        Reward-share proofs were removed from the orchestrator runtime.

        BeamCore owns proof verification and the orchestrator no longer writes
        epoch payment artifacts or local payment records.
        """
        active_workers = [
            worker
            for worker in workers_values
            if worker.rewards_earned_epoch > 0 or worker.bytes_relayed_epoch > 0
        ]
        if active_workers:
            logger.info(
                "Skipping deprecated reward-share proof generation for epoch %s (%s active workers)",
                epoch,
                len(active_workers),
            )
        return None
