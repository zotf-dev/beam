"""
BEAM Orchestrator Entry Point

Run with: python -m neurons.orchestrator.main

The Orchestrator coordinates bandwidth tasks with BeamCore:
- Registers with BeamCore HTTP on startup
- Keeps a live WebSocket session to the orchestrator gateway (upstream BeamCore relay) for assignments and control updates
- Relies on that push channel for the hot path (HTTP polling helpers exist only for legacy compatibility)
- Manages the orchestrator's advertised worker pool and forwards worker outcomes upstream to BeamCore

Architecture:
┌────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR                               │
│                                                                    │
│  BeamCore ◀──── Register / orch-gateway WS ──────▶ Assignments    │
│      │                                              │              │
│      ▼                                              ▼              │
│  Payment Reports ◀── Task Summaries ◀──── Worker Pool metadata     │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

Transfer execution happens on workers that dial the **worker-gateway** endpoints advertised by BeamCore.
Orchestrators still coordinate exclusively through BeamCore APIs rather than talking to arbitrary workers directly.
"""

import logging
import os
import socket
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.orchestrator import Orchestrator, get_orchestrator
from middleware.metrics import MetricsMiddleware, get_metrics_collector, get_metrics_response
from middleware.rate_limiting import RateLimitMiddleware, get_rate_limiter
from routes import health, orchestrators

# WebSocket registration, keepalive, and transfer flow are owned by
# SubnetCoreClient. main.py only wires lifespan + FastAPI routes.


# Configure logging - both console and file
LOG_DIR = os.environ.get("LOG_DIR", "/tmp/beam_logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
log_datefmt = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=log_datefmt,
)

# Add file handler for log viewer
file_handler = logging.FileHandler(f"{LOG_DIR}/orchestrator.log")
file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)

# Global instances
orchestrator: Orchestrator = None


def _get_local_ip() -> str:
    """Best-effort local outbound IP (registration URL when EXTERNAL_IP is unset)."""
    try:
        # Create a socket to determine the outbound IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global orchestrator

    settings = get_settings()

    # Configure logging level
    logging.getLogger().setLevel(settings.log_level)

    # Initialize rate limiter
    rate_limiter = get_rate_limiter()
    await rate_limiter.start_cleanup()

    # Rate limit configs for legacy endpoints removed
    # All worker/transfer coordination now handled by BeamCore

    # Initialize metrics collector
    metrics_collector = get_metrics_collector()

    # Initialize orchestrator
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # Client authentication removed - auth handled by BeamCore

    # Link metrics collector to orchestrator
    metrics_collector.set_orchestrator(orchestrator)
    await metrics_collector.start()

    # Start orchestrator background tasks
    await orchestrator.start()

    logger.info("=" * 60)
    logger.info("BEAM Orchestrator started")
    logger.info("=" * 60)
    logger.info(f"Hotkey: {orchestrator.hotkey}")
    logger.info(f"Network: {settings.subtensor_network}")
    logger.info(f"Subnet: {settings.netuid}")
    logger.info(f"API: http://{settings.api_host}:{settings.api_port}")
    logger.info("=" * 60)

    # WebSocket connection (registration + keepalive + transfer flow) is owned by
    # SubnetCoreClient. It auto-registers via WS using the config set in
    # _init_subnet_core_client and obtains an API key via /auth/challenge + /auth/verify.
    if orchestrator.subnet_core_client:
        api_key = orchestrator.subnet_core_client._api_key
        if api_key:
            logger.info("SubnetCoreClient API key cached in memory (%s...)", api_key[:20])
        else:
            logger.info(
                "SubnetCoreClient API key: not fetched yet — first orch-gateway websocket connect "
                "will run HTTP auth/challenge+verify in the background; set BEAMCORE_API_KEY to skip this step "
            )
    else:
        logger.warning("No subnet_core_client available")
    logger.info("WebSocket connection handled by SubnetCoreClient")

    # Signal readiness to receive transfers through the orchestrator WS relay.
    if settings.ready and orchestrator.subnet_core_client:
        try:
            applied = await orchestrator.subnet_core_client.set_ready(True)
            if applied:
                logger.info(
                    "Signalled ready=True through orch-gateway — orchestrator will receive transfers"
                )
            else:
                logger.info(
                    "Queued ready=True — it will be applied after orch-gateway registration completes"
                )
        except Exception as e:
            logger.warning(f"Failed to set ready=True through orch-gateway: {e}")
    else:
        logger.info(
            "ready=False (default) — orchestrator will NOT receive transfers until READY=true is set"
        )

    yield

    # Cleanup
    logger.info("Shutting down BEAM Orchestrator...")

    # Signal not-ready before stopping so BeamCore stops routing traffic immediately
    if orchestrator.subnet_core_client:
        try:
            applied = await orchestrator.subnet_core_client.set_ready(False)
            if applied:
                logger.info(
                    "Signalled ready=False through orch-gateway — orchestrator removed from routing"
                )
            else:
                logger.info("Queued ready=False while websocket is offline during shutdown")
        except Exception as e:
            logger.warning(f"Failed to set ready=False through orch-gateway during shutdown: {e}")

    await orchestrator.stop()
    await metrics_collector.stop()
    await rate_limiter.stop_cleanup()

    logger.info("BEAM Orchestrator stopped")


# Create FastAPI app
app = FastAPI(
    title="BEAM Orchestrator",
    description="""
BEAM Orchestrator - Decentralized bandwidth mining coordinator.

The Orchestrator connects to BeamCore and:
- Registers with BeamCore on startup
- Maintains a live WebSocket control-plane session
- Receives transfer assignments from BeamCore
- Manages local worker pools and task distribution
- Submits proof-of-bandwidth to BeamCore

All worker registration, transfer coordination, and validator communication
is handled centrally by BeamCore.

## Endpoints

### Health
Monitor the Orchestrator's health and view metrics.

### Orchestrators
Registration and readiness endpoints for BeamCore communication.
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# Add middleware (order matters - first added = last to process request)
app.add_middleware(MetricsMiddleware, metrics_collector=get_metrics_collector())
app.add_middleware(RateLimitMiddleware, rate_limiter=get_rate_limiter())

# Add CORS middleware if configured
_cors_settings = get_settings()
_cors_origins = _cors_settings.get_cors_origins()
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_settings.cors_allow_credentials,
        allow_methods=_cors_settings.get_cors_methods(),
        allow_headers=_cors_settings.get_cors_headers(),
    )
    logger.info(f"CORS enabled for origins: {_cors_origins}")

# Mount route modules
app.include_router(health.router)
app.include_router(orchestrators.router)


# =============================================================================
# Additional API Routes
# =============================================================================




@app.websocket("/ws/{worker_id}")
async def worker_gateway_ws(websocket: WebSocket, worker_id: str):
    """Local dedicated worker-gateway WebSocket endpoint.

    Workers connect here when WORKER_GATEWAY_URL points at this orchestrator,
    for example WORKER_GATEWAY_URL=http://127.0.0.1:8000.  This endpoint keeps
    the worker socket in the orchestrator's local WorkerManager so the scheduler
    can push task_offer messages to dedicated workers instead of relying on the
    Beam-hosted public worker gateway.
    """
    await websocket.accept()

    if orchestrator is None:
        await websocket.close(code=1013, reason="orchestrator_not_ready")
        return

    # Ensure the local worker exists in the orchestrator cache.  Workers still
    # self-register with BeamCore over HTTP; this local registration only makes
    # the socket selectable by this orchestrator.
    try:
        if not orchestrator.get_worker(worker_id):
            await orchestrator.register_worker(
                hotkey=worker_id,
                ip=websocket.client.host if websocket.client else "127.0.0.1",
                port=websocket.client.port if websocket.client else 0,
                region="local",
                bandwidth_mbps=0.0,
            )
        orchestrator.register_worker_connection(worker_id, websocket)
        logger.info("Dedicated worker connected: %s", worker_id)

        await websocket.send_json({"type": "connected", "worker_id": worker_id})

        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "stats_snapshot":
                bandwidth_mbps = float(message.get("bandwidth_mbps") or 0.0)
                active_tasks = int(message.get("tasks_active") or message.get("active_tasks") or 0)
                bytes_delta = int(message.get("bytes_relayed_delta") or 0)
                await orchestrator.apply_worker_stats_snapshot(
                    worker_id, bandwidth_mbps, active_tasks, bytes_delta
                )
                await websocket.send_json({"type": "stats_snapshot_ack", "worker_id": worker_id})

            elif msg_type == "task_accept":
                task_id = message.get("task_id")
                offer_id = message.get("offer_id") or task_id
                accepted = True
                reason = None
                try:
                    # For orchestrator-originated local offers, this enforces the
                    # one-winner offer semantics.  For BeamCore-originated exact
                    # chunk offers, there may be no local PendingOffer, so we still
                    # ACK to keep the worker inside the 5s accept window.
                    if offer_id and hasattr(orchestrator, "accept_task_offer"):
                        ok, _chunk_data, _metadata = await orchestrator.accept_task_offer(
                            offer_id, worker_id
                        )
                        if ok is not None:
                            accepted = bool(ok) or offer_id == task_id
                except Exception as exc:
                    logger.debug("Local task_accept bookkeeping skipped: %s", exc)
                await websocket.send_json(
                    {
                        "type": "task_accept_ack",
                        "task_id": task_id,
                        "offer_id": offer_id,
                        "accepted": accepted,
                        "reason": reason,
                    }
                )

            elif msg_type == "task_reject":
                offer_id = message.get("offer_id") or message.get("task_id")
                reason = message.get("reason") or "rejected"
                try:
                    await orchestrator.reject_task_offer(offer_id, worker_id, reason)
                except Exception:
                    pass
                await websocket.send_json(
                    {
                        "type": "task_accept_ack",
                        "task_id": message.get("task_id"),
                        "offer_id": offer_id,
                        "accepted": False,
                        "reason": reason,
                    }
                )

            elif msg_type == "task_result_summary":
                # Forward worker completion upstream over the orchestrator control
                # websocket.  The worker submits PoB directly after receiving this
                # ACK, matching the guide's Worker -> BeamCore evidence flow.
                task_id = message.get("task_id")
                offer_id = message.get("offer_id") or task_id
                received = False
                completed = False
                reason = None
                try:
                    if orchestrator.subnet_core_client and orchestrator.subnet_core_client._ws:
                        import json as _json

                        upstream = dict(message)
                        upstream.setdefault("worker_id", worker_id)
                        await orchestrator.subnet_core_client._ws.send(_json.dumps(upstream))
                        received = True
                        completed = bool(message.get("success", False))
                    else:
                        reason = "orchestrator_ws_not_connected"
                except Exception as exc:
                    reason = str(exc)
                    logger.warning("Failed to forward task_result_summary upstream: %s", exc)

                await websocket.send_json(
                    {
                        "type": "task_result_summary_ack",
                        "task_id": task_id,
                        "offer_id": offer_id,
                        "received": received,
                        "completed": completed,
                        "reason": reason,
                    }
                )

            elif msg_type == "bw_challenge_response":
                await websocket.send_json(
                    {
                        "type": "bw_challenge_ack",
                        "challenge_id": message.get("challenge_id"),
                        "worker_id": worker_id,
                    }
                )

            else:
                logger.debug("Unknown dedicated worker message from %s: %s", worker_id, msg_type)

    except WebSocketDisconnect:
        logger.info("Dedicated worker disconnected: %s", worker_id)
    except Exception as exc:
        logger.warning("Dedicated worker websocket error for %s: %s", worker_id, exc)
    finally:
        if orchestrator is not None:
            orchestrator.unregister_worker_connection(worker_id)

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "BEAM Orchestrator",
        "version": "0.1.0",
        "description": "Central coordinator for decentralized bandwidth mining",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/state")
async def get_state():
    """Get full Orchestrator state."""
    if orchestrator:
        return orchestrator.get_state()
    return {"error": "Orchestrator not initialized"}


@app.get("/workers/stats")
async def get_worker_stats():
    """Get detailed worker statistics."""
    if orchestrator:
        return orchestrator.get_worker_stats()
    return {"error": "Orchestrator not initialized"}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import Response

    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)


@app.get("/metrics/json")
async def metrics_json():
    """JSON metrics endpoint for non-Prometheus consumers."""
    metrics_collector = get_metrics_collector()
    rate_limiter = get_rate_limiter()

    return {
        "uptime_seconds": time.time() - metrics_collector._start_time,
        "orchestrator": orchestrator.get_state() if orchestrator else {},
        "rate_limiter": rate_limiter.get_stats(),
    }


# =============================================================================
# Main
# =============================================================================


def main():
    """Main entry point."""
    settings = get_settings()

    # Print banner
    print("""
╔═══════════════════════════════════════════════════╗
║                                                   ║
║        ██████╗ ███████╗ █████╗ ███╗   ███╗        ║
║        ██╔══██╗██╔════╝██╔══██╗████╗ ████║        ║
║        ██████╔╝█████╗  ███████║██╔████╔██║        ║
║        ██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║        ║
║        ██████╔╝███████╗██║  ██║██║ ╚═╝ ██║        ║
║        ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝        ║
║                                                   ║
║                   ORCHESTRATOR                    ║
║    Decentralized Bandwidth Mining Coordinator     ║
║                                                   ║
╚═══════════════════════════════════════════════════╝
    """)

    # Auto-open log viewer in browser (disabled by default, set OPEN_LOG_VIEWER=true to enable)
    if os.environ.get("OPEN_LOG_VIEWER", "").lower() in ("true", "1", "yes"):
        import threading
        import webbrowser

        log_viewer_url = os.environ.get("LOG_VIEWER_URL", "https://beamcore.b1m.ai/logs/")

        def open_logs():
            time.sleep(1.5)  # Wait for server to start
            webbrowser.open(log_viewer_url)

        threading.Thread(target=open_logs, daemon=True).start()

    # Run server
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
