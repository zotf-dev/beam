# BEAM Validator Guide

Run a validator on BEAM mainnet.

## Public Endpoint

| Service | Environment variable | URL |
| ------- | -------------------- | --- |
| Core server | `BEAM_VALIDATOR_CORE_SERVER_URL` | `https://beamcore.b1m.ai` |

## Requirements

- Python 3.10-3.12
- A Bittensor wallet with a registered validator hotkey on subnet 105
- Sufficient TAO stake for validation

## Install

```bash
git clone https://github.com/Beam-Network/beam.git
cd beam
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[validator]"
```

## Register

```bash
btcli subnet register --netuid 105 --subtensor.network finney \
  --wallet.name your_coldkey \
  --wallet.hotkey your_hotkey
```

## Configure

Create `neurons/validator/.env`:

```bash
BEAM_VALIDATOR_CORE_SERVER_URL=https://beamcore.b1m.ai
SUBTENSOR_NETWORK=finney
NETUID=105

BEAM_VALIDATOR_WALLET_NAME=your_coldkey
BEAM_VALIDATOR_WALLET_HOTKEY=your_hotkey
BEAM_VALIDATOR_WALLET_PATH=~/.bittensor/wallets

BEAM_VALIDATOR_LOG_LEVEL=INFO
```

## Run

```bash
cd neurons/validator
python main.py
```

Useful health checks:

```bash
curl http://localhost:8093/health
curl http://localhost:8093/state | jq
curl "$BEAM_VALIDATOR_CORE_SERVER_URL/health"
```

## systemd

Use `/srv/beam/beam` as the example checkout path below. Adjust paths if you deploy elsewhere.

```ini
[Unit]
Description=BEAM Validator
After=network.target

[Service]
Type=simple
User=beam
WorkingDirectory=/srv/beam/beam/neurons/validator
Environment="PATH=/srv/beam/beam/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/srv/beam/beam/neurons/validator/.env
ExecStart=/srv/beam/beam/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

- Verify the hotkey is registered on subnet 105.
- Verify `BEAM_VALIDATOR_CORE_SERVER_URL=https://beamcore.b1m.ai`.
- Confirm the validator process can reach `https://beamcore.b1m.ai/health`.
