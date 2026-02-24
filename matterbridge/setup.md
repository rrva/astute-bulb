# Matterbridge Setup Guide

This guide explains how to set up Matterbridge to expose your lamps as Matter devices for Google Home.

## Prerequisites

- Node.js 20 LTS or 22 LTS installed
- IPv6 enabled on your local network
- The lamp-service running on port 8000

## Installation

1. **Install Matterbridge globally:**

```bash
npm install -g matterbridge
```

2. **Install the webhooks plugin:**

```bash
npm install -g matterbridge-webhooks

# Verify the binary is available
which matterbridge
```

3. **Start Matterbridge:**

```bash
matterbridge
```

4. **Open the Matterbridge web interface:**

Open http://localhost:8283 in your browser.

## Configure Webhooks

For each lamp in your configuration, you need to set up webhooks in the Matterbridge web interface.

### Example: Living Room Light

Assuming your lamp-service runs on `http://192.168.1.50:8000` and you have a lamp with ID `living_room`:

1. Go to the **Plugins** section and add `matterbridge-webhooks`

2. Configure the plugin with your lamps. For each lamp, create an **extendedLight** device:

**Device Name:** `Living Room Light`
**Device Type:** `extendedLight`

**Webhooks:**

| Action | Method | URL |
|--------|--------|-----|
| Turn On | GET | `http://192.168.1.50:8000/webhook/living_room/on` |
| Turn Off | GET | `http://192.168.1.50:8000/webhook/living_room/off` |
| Set Brightness | GET | `http://192.168.1.50:8000/webhook/living_room/brightness?level=${LEVEL}` |
| Set Color Temp | GET | `http://192.168.1.50:8000/webhook/living_room/temperature?kelvin=${KELVIN}` |
| Set Color | GET | `http://192.168.1.50:8000/webhook/living_room/color?hue=${HUE}&saturation=${SATURATION}&level=${LEVEL}` |

### Webhook URL Templates

Replace `{IP}` with your lamp-service IP and `{LAMP_ID}` with your lamp's ID:

```
Turn On:       http://{IP}:8000/webhook/{LAMP_ID}/on
Turn Off:      http://{IP}:8000/webhook/{LAMP_ID}/off
Brightness:    http://{IP}:8000/webhook/{LAMP_ID}/brightness?level=${LEVEL}
Color Temp:    http://{IP}:8000/webhook/{LAMP_ID}/temperature?kelvin=${KELVIN}
Color (HSV):   http://{IP}:8000/webhook/{LAMP_ID}/color?hue=${HUE}&saturation=${SATURATION}&level=${LEVEL}
Color (RGB):   http://{IP}:8000/webhook/{LAMP_ID}/color?red=${red}&green=${green}&blue=${blue}
```

## Pair with Google Home

1. In the Matterbridge web interface, go to the main page
2. You'll see a **QR code** for pairing
3. Open the **Google Home app** on your phone
4. Tap **+** → **Set up device** → **Matter-enabled device**
5. Scan the QR code from Matterbridge
6. Accept the "Uncertified device" warning
7. Your lamps should appear in Google Home!

## Troubleshooting

### "Device not found" errors

- Make sure the lamp-service is running: `curl http://localhost:8000/health`
- Check that the lamp ID in the webhook URL matches your config

### QR code won't scan

- Make sure IPv6 is enabled on your network
- Ensure your phone and Mac are on the same network
- Try entering the pairing code manually (shown below QR code)

### Commands are slow

- The first command after a lamp has been idle may take 1-2 seconds
- Subsequent commands should be faster due to persistent connections

### Google Home says "Something went wrong"

- Check Matterbridge logs for errors
- Verify the webhook URLs are correct
- Make sure the lamp-service is accessible from the Matterbridge host

## Running Matterbridge as a Service

To run Matterbridge automatically on startup:

### macOS (launchd)

Create `~/Library/LaunchAgents/com.matterbridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.matterbridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/matterbridge</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/matterbridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/matterbridge.err</string>
</dict>
</plist>
```

Load the service:

```bash
launchctl load ~/Library/LaunchAgents/com.matterbridge.plist
```

### Linux (systemd)

Create `/etc/systemd/system/matterbridge.service`:

```ini
[Unit]
Description=Matterbridge
After=network.target

[Service]
Type=simple
User=YOUR_USER
ExecStart=/usr/bin/matterbridge
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable matterbridge
sudo systemctl start matterbridge
```
