# Run Beam with 1 orchestrator + 2 workers

First edit `.env` with your real wallet values. Keep:

```env
CORE_SERVER_URL=https://beamcore.b1m.ai
ORCH_GATEWAY_URL=https://orch-gateway.b1m.ai
WORKER_GATEWAY_URL=https://public-worker-gateway.b1m.ai
SUBTENSOR_NETWORK=finney
NETUID=105
ORCHESTRATOR_UID=73
READY=true
WORKER_REQUIRED_PAYMENT=false
```

## Terminal 1 — orchestrator

```bash
cd beam-main
cp .env.example .env
# edit .env: WALLET_NAME, WALLET_HOTKEY, WALLET_PATH, ORCHESTRATOR_UID=73
python -m neurons.orchestrator.main
```

## Terminal 2 — worker 1

```bash
cd beam-main
export CORE_SERVER_URL=https://beamcore.b1m.ai
export WORKER_GATEWAY_URL=https://public-worker-gateway.b1m.ai
export WORKER_REQUIRED_PAYMENT=false
python -m neurons.worker.worker --wallet.name <your_wallet> --wallet.hotkey <your_hotkey>
```

## Terminal 3 — worker 2

```bash
cd beam-main
export CORE_SERVER_URL=https://beamcore.b1m.ai
export WORKER_GATEWAY_URL=https://public-worker-gateway.b1m.ai
export WORKER_REQUIRED_PAYMENT=false
python -m neurons.worker.worker --wallet.name <your_wallet> --wallet.hotkey <your_hotkey>
```

cd /work/beam/neurons/orchestrator || exit 1
export PYTHONPATH=/work/beam/neurons/orchestrator
export READY=true
export USE_LOCAL_WORKER_GATEWAY=true
export WORKER_GATEWAY_PUBLIC_URL=http://127.0.0.1:8000
python3 main.py


cd /work/beam || exit 1
export CORE_SERVER_URL=https://beamcore.b1m.ai
export WORKER_GATEWAY_URL=http://127.0.0.1:8000
export WORKER_REQUIRED_PAYMENT=false
python3 -m neurons.worker.worker worker worker01