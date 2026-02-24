# Local Lamps

Local control solution for Ledvance Sun@Home lamps with Google Home integration.

**No cloud dependency for lamp control** - only Google's voice recognition uses the cloud; all lamp commands travel locally on your network.

## Why

The Ledvance Sun@Home lamps are great hardware, but the cloud-based control through the Ledvance/Tuya app has real problems. Commands sometimes lag noticeably, and occasionally lamps just fail to turn on or off — not what you want when flipping lights before bed. By talking directly to the lamps over your local network using the Tuya protocol, commands are fast and reliable.

This project also adds proper circadian lighting. When you turn a lamp on, it automatically matches its color temperature and brightness to the current sun position — warm and dim in the evening, bright and cool during the day. And while lamps stay on, a background task continuously adjusts them to follow the sun, so your lighting shifts naturally throughout the day without you touching anything.

## Architecture

```
Google Home Speaker -> (voice to cloud) -> Google Cloud (voice recognition only)
                                              |
                                         (local Matter)
                                              |
Mac Mini running:                        Matterbridge
  - Lamp Service (Python)          <-- webhooks plugin
  - Matterbridge (Node.js)
        |
  Tuya Protocol 3.5 (local WiFi)
        |
  Ledvance Sun@Home Lamps
```

## Features

- **Local Control**: Control lamps via REST API without internet
- **Google Home Integration**: Voice control through Matter protocol
- **Solar-Aware Circadian Lighting**: Brightness and color temperature automatically follow the sun's position
- **Full Lamp Support**: On/off, brightness, color temperature, RGB colors
- **Multiple Lamp Types**: Works with Sun@Home E27 bulbs, panels, and more

## Quick Start

### 1. Extract Local Keys

You need the Tuya encryption keys for your Ledvance lamps. Use one of:

- [tinytuya wizard](https://github.com/jasonacox/tinytuya#setup-wizard---getting-local-keys) - interactive key extraction via Tuya IoT Platform
- [FlagX/ha-ledvance-tuya-resync-localkey](https://github.com/FlagX/ha-ledvance-tuya-resync-localkey) - Ledvance-specific key extraction

Once you have the keys, copy `config/lamps.example.yaml` to `config/lamps.yaml` and fill in your device IDs, IPs, and local keys.

### 2. Install Lamp Service

```bash
cd lamp-service
uv sync --group dev
```

### 3. Start the Service

```bash
# Set config path
export LAMPS_CONFIG="../config/lamps.yaml"

# Run the service
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### 4. Test Local Control

```bash
# List all lamps
curl http://localhost:8000/lamps

# Turn on a lamp
curl -X POST http://localhost:8000/lamps/living_room/on

# Set brightness to 50%
curl -X POST http://localhost:8000/lamps/living_room/brightness \
  -H "Content-Type: application/json" \
  -d '{"brightness": 50}'

# Set color temperature to warm white (2700K)
curl -X POST http://localhost:8000/lamps/living_room/temperature \
  -H "Content-Type: application/json" \
  -d '{"temperature": 2700}'
```

### 5. Set Up Google Home Integration

See [matterbridge/setup.md](matterbridge/setup.md) for detailed Matterbridge setup instructions.

Quick version:

```bash
# Install Matterbridge
npm install -g matterbridge matterbridge-webhooks

# Start Matterbridge
matterbridge
```

Open http://localhost:8283, configure webhooks for your lamps, then pair with Google Home using the QR code.

## Running as macOS Services

The `scripts/` directory includes launchd plist templates to run services automatically. All contain `YOUR_USER` placeholders that must be replaced with your macOS username.

### Lamp Service

```bash
sudo cp scripts/com.local-lamps.plist /Library/LaunchDaemons/
sudo sed -i '' "s/YOUR_USER/$(whoami)/g" /Library/LaunchDaemons/com.local-lamps.plist
sudo launchctl load -w /Library/LaunchDaemons/com.local-lamps.plist
```

Logs: `~/Library/Logs/local-lamps.log`, `~/Library/Logs/local-lamps.err`

### Matterbridge

The Matterbridge plist also requires replacing `YOUR_IP` with your Mac's local IP address (for Matter mDNS advertisement).

```bash
sudo cp scripts/com.matterbridge.plist /Library/LaunchDaemons/
sudo sed -i '' "s/YOUR_USER/$(whoami)/g" /Library/LaunchDaemons/com.matterbridge.plist
sudo sed -i '' "s/YOUR_IP/$(ipconfig getifaddr en1)/g" /Library/LaunchDaemons/com.matterbridge.plist
sudo launchctl load -w /Library/LaunchDaemons/com.matterbridge.plist
```

Logs: `~/Library/Logs/matterbridge.log`, `~/Library/Logs/matterbridge.err`

### Static ARP Entries

Keeps Tuya devices reachable by loading static ARP entries at boot. See [Troubleshooting](#lamps-unreachable-or-timing-out-arp-issue) for why this is needed.

```bash
sudo cp scripts/com.local.static-arp.plist /Library/LaunchDaemons/
sudo sed -i '' "s/YOUR_USER/$(whoami)/g" /Library/LaunchDaemons/com.local.static-arp.plist
sudo launchctl load -w /Library/LaunchDaemons/com.local.static-arp.plist
```

### Unloading Services

```bash
sudo launchctl unload /Library/LaunchDaemons/com.local-lamps.plist
sudo launchctl unload /Library/LaunchDaemons/com.matterbridge.plist
sudo launchctl unload /Library/LaunchDaemons/com.local.static-arp.plist
```

## API Reference

### Lamps

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (reports stuck error-914 devices) |
| `/lamps` | GET | List all lamps with status |
| `/lamps/{id}/status` | GET | Get lamp status |
| `/lamps/{id}/on` | POST | Turn lamp on |
| `/lamps/{id}/off` | POST | Turn lamp off |
| `/lamps/{id}/brightness` | POST | Set brightness (0-100%) |
| `/lamps/{id}/temperature` | POST | Set color temp (Kelvin) |
| `/lamps/{id}/color` | POST | Set RGB color |

### Webhook Endpoints (for Matterbridge)

| Endpoint | Description |
|----------|-------------|
| `/webhook/{id}/on` | Turn on (GET) |
| `/webhook/{id}/off` | Turn off (GET) |
| `/webhook/{id}/brightness?level={0-100}` | Set brightness |
| `/webhook/{id}/temperature?kelvin={K}` or `?mired={M}` | Set color temp |
| `/webhook/{id}/color?hue={H}&saturation={S}&level={L}` or `?red={R}&green={G}&blue={B}` | Set color (HSV or RGB) |

## Configuration

### config/lamps.yaml

```yaml
service:
  host: "0.0.0.0"
  port: 8000

lamps:
  - id: living_room
    name: "Living Room Light"
    device_id: "abc123..."
    ip: "192.168.1.100"
    local_key: "xyz789..."
    version: "3.5"
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LAMPS_CONFIG` | Path to config file | Searches `config/lamps.yaml` in cwd, repo root, and `~/.config/local-lamps/` |

## Network Requirements

### Firewall Ports

- **TCP 6668**: Tuya device communication
- **UDP 6666, 6667, 7000**: Tuya device discovery
- **TCP 8000**: Lamp service API
- **TCP 8283**: Matterbridge web interface
- **UDP 5353**: mDNS (Matter discovery)
- **TCP/UDP 5540**: Matter protocol

## Troubleshooting

### "Device not responding"

1. Check lamp IP address is correct (may have changed via DHCP)
2. Run `uv run tinytuya scan` to find devices on network
3. Verify local_key is correct (re-extract keys if needed)

### "Error: key length error"

The local key must be exactly 16 characters. Re-run the key extraction.

### Lamp responds slowly

First command after idle may take 1-2 seconds as connection is established. Subsequent commands are faster.

### Lamps unreachable or timing out (ARP issue)

Tuya devices are poor ARP responders — they often fail to reply to ARP requests, causing your machine to lose track of their MAC addresses. When this happens, the OS can't resolve the lamp's IP to a physical address and connections fail silently or time out.

Fix this with static ARP entries using `scripts/static-arp.sh`. Edit the script with your lamp IPs and MAC addresses, then run it (requires root):

```bash
sudo bash scripts/static-arp.sh
```

You can find MAC addresses with `arp -a` while the lamps are still reachable, or check your router's DHCP client list. Re-run the script after each reboot, or add it to your startup items.

### Google Home says "Something went wrong"

1. Check Matterbridge logs
2. Verify webhook URLs are accessible
3. Ensure lamp service is running

## Project Structure

```
local-lamps/
├── config/
│   ├── lamps.yaml              # Your lamp configuration (gitignored)
│   └── lamps.example.yaml      # Example configuration
├── lamp-service/
│   ├── pyproject.toml          # Python dependencies
│   ├── src/
│   │   ├── main.py             # FastAPI application
│   │   ├── lamp_controller.py  # TinyTuya wrapper
│   │   ├── solar.py            # Sun position → lamp values
│   │   ├── config.py           # Configuration loader
│   │   └── models.py           # Pydantic models
│   └── tests/
│       ├── test_config.py
│       ├── test_lamp_controller.py
│       ├── test_models.py
│       └── test_solar.py
├── scripts/
│   ├── start_services.sh       # Service startup script
│   ├── com.local-lamps.plist   # launchd daemon: lamp service (replace YOUR_USER)
│   ├── com.matterbridge.plist  # launchd daemon: Matterbridge (replace YOUR_USER, YOUR_IP)
│   ├── com.local.static-arp.plist # launchd daemon: static ARP (replace YOUR_USER)
│   └── static-arp.sh           # Static ARP entries for Tuya devices
├── matterbridge/
│   └── setup.md                # Matterbridge setup guide
└── README.md
```

## Credits

- [TinyTuya](https://github.com/jasonacox/tinytuya) - Python library for local Tuya device control
- [FlagX/ha-ledvance-tuya-resync-localkey](https://github.com/FlagX/ha-ledvance-tuya-resync-localkey) - Ledvance key extraction
- [Matterbridge](https://github.com/Luligu/matterbridge) - Matter bridge platform
- [matterbridge-webhooks](https://github.com/Luligu/matterbridge-webhooks) - Webhook plugin for Matterbridge

## License

MIT
