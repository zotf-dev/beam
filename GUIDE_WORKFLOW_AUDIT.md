# Beam Guide Workflow Audit

Use this file to verify the code with your eyes against the guide screenshots.

## Required guide flow

```text
BeamCore/orch-gateway
  -> transfer_assigned
  -> orchestrator lists eligible connected workers
  -> orchestrator sends chunk_assignments quickly (~5s window)
  -> worker-gateway sends task_offer to worker
  -> worker sends task_accept and waits for task_accept_ack (~5s)
  -> worker downloads source chunk
  -> worker uploads destination chunk
  -> worker computes chunk_hash/metrics
  -> worker sends task_result_summary
  -> worker waits for task_result_summary_ack
  -> worker submits payment/proof evidence directly to BeamCore HTTP
```

## Files patched

### `neurons/orchestrator/clients/subnet_core_client.py`

Check `_handle_transfer_assigned()`.

What changed:
- `transfer_assigned` hot path now uses a max 4 second timeout.
- Removed the old 5-attempt retry loop that could take much longer than BeamCore's recovery window.
- `list_public_workers` request gets a unique request id: `workers:<assignment>`.
- `chunk_assignments` request gets a unique request id: `chunks:<assignment>`.
- Sends `transfer_id` together with `assignment_id` and `assignments`.
- Scores workers by trust, bandwidth, and active load.

This matches the guide requirement that assignment must be fast after `transfer_assigned`.

### `neurons/worker/worker.py`

Check:
- `WORKER_REQUIRED_PAYMENT`
- `WS_TASK_RESULT_ACK_TIMEOUT`
- `handle_ws_task()`
- `ws_send_task_accept()`
- `finalize_ws_task_result()`
- `submit_worker_payment_evidence()`

What changed:
- `WORKER_REQUIRED_PAYMENT` defaults to `false` for bandwidth proof mode.
- `task_result_summary_ack` wait timeout is now 5 seconds.

Already present in original code and verified:
- Worker receives `task_offer`.
- Worker sends `task_accept`.
- Worker waits for `task_accept_ack` within 5 seconds.
- Worker executes download/upload.
- Worker sends `task_result_summary`.
- Worker waits for `task_result_summary_ack`.
- Worker submits evidence directly to BeamCore HTTP after successful completion.

### `.env.example` and `neurons/orchestrator/.env.example`

What changed:
- `NETUID=105` remains set.
- `ORCHESTRATOR_UID=73` added as your miner UID placeholder.
- `READY=true` is enabled so BeamCore can route transfers.
- `WORKER_REQUIRED_PAYMENT=false` enabled for worker proof mode.

## Eye-check commands

```bash
grep -R "transfer_assigned" -n neurons/orchestrator/clients/subnet_core_client.py
grep -R "chunk_assignments" -n neurons/orchestrator/clients/subnet_core_client.py
grep -R "task_offer" -n neurons/orchestrator/core/task_scheduler.py neurons/worker/worker.py
grep -R "task_accept" -n neurons/worker/worker.py
grep -R "task_result_summary" -n neurons/worker/worker.py neurons/orchestrator/clients/subnet_core_client.py
grep -R "WORKER_REQUIRED_PAYMENT\|READY\|NETUID\|ORCHESTRATOR_UID" -n .env.example neurons/orchestrator/.env.example neurons/worker/worker.py neurons/orchestrator/core/config.py
```

## Expected runtime log sequence

```text
Registration acknowledged
Signalled ready=True
transfer_assigned
Queued ... worker tasks from ... chunk_assignments
[Worker] [WS] Task: ...
[Worker] [WS] Task completed on BeamCore
[Worker] Payment evidence OK
```

## Important limitation

I can verify the repo compiles and the guide-required code paths exist. I cannot prove live reward/payment success without your real wallet, UID registration, worker gateway access, and a live transfer from BeamCore.
