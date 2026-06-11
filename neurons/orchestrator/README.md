# Beam Orchestrator

Orchestrators coordinate worker capacity and receive transfer assignments through the public BEAM control plane.

## Install

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "."
```

## Configure

```bash
CORE_SERVER_URL=https://beamcore.b1m.ai
ORCH_GATEWAY_URL=https://orch-gateway.b1m.ai
SUBTENSOR_NETWORK=finney
NETUID=105
WALLET_NAME=your_coldkey
WALLET_HOTKEY=your_hotkey
```

## Run

```bash
cd neurons/orchestrator
python main.py
```

## Environment

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `CORE_SERVER_URL` | Beam control-plane HTTP base | `https://beamcore.b1m.ai` |
| `ORCH_GATEWAY_URL` | Orchestrator WebSocket gateway | required |
| `SUBTENSOR_NETWORK` | Bittensor network | `finney` |
| `NETUID` | BEAM subnet UID | `105` |
| `WALLET_NAME` | Bittensor coldkey name | `orchestrator` |
| `WALLET_HOTKEY` | Bittensor hotkey name | `default` |
| `READY` | Signals readiness for transfer routing | `false` |

See [../../docs/orchestrator.md](../../docs/orchestrator.md) for the full operator guide.
