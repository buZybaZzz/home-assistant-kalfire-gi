# Kalfire Gi Local for Home Assistant

An independent Home Assistant integration for Kalfire **Gi** gas fireplaces using the local encrypted CoAP/DTLS interface. No Kalfire cloud account, MQTT broker, relay wiring or custom firmware is required by this integration.

**Early beta, validated on one Gi with communication-board firmware 0.7.11 and Home Assistant 2026.10.2.** It is not a Kalfire product and is not endorsed by Kalfire or iQontrol. Other Kalfire product families, including older iMatch fireplaces, are not supported.

## Features

- Local temperature, operating state, error code and flame-height **setting** sensors.
- Firmware version in device information; optional raw status bits for diagnostics.
- Setup through **Settings → Devices & services → Add integration → Kalfire Gi Local**.
- Physical pairing with the official remote; alternatively import an existing local device token.
- Explicitly accepted SHA256 certificate pin, checked on every connection.
- Optional normal on/off switch, enabled through integration options. Controls are off by default.
- Address reconfiguration, reauthentication, redacted diagnostics and Dutch/English UI.

The flame-height sensor reports a stored setting, **not** proof of a flame. The state follows the device's own state machine. No ignition, reset or other control command is sent by setup, pairing, polling, reloading or reconnecting.

## Install with HACS

The repository can be used as a **custom repository**; inclusion in HACS's default directory is a separate future review.

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/buZybaZzz/home-assistant-kalfire-gi`, category **Integration**.
3. Download **Kalfire Gi Local**. Enable beta versions if installing a prerelease.
4. Restart Home Assistant once to load the custom integration.
5. Add **Kalfire Gi Local** under Devices & services.

Manual alternative: copy `custom_components/kalfire_gi/` into `/config/custom_components/kalfire_gi/` and restart Home Assistant. All runtime files are in that one directory. A separate compiled executable is not needed.

## Pair your fireplace

Keep the fireplace's official remote paired and in its normal location near the fireplace. The remote and the fireplace's existing safety functions remain necessary.

1. Put Home Assistant and the fireplace on the same trusted LAN/subnet for the initial setup. Allow unicast UDP 5684. Cross-subnet support has not been established; no broad firewall opening or port forwarding is needed.
2. Find the fireplace IP address in your router. A DHCP reservation is useful but optional.
3. Enter that address in the integration setup. The default port is 5684.
4. Check the device address and explicitly accept the displayed certificate fingerprint on your trusted network. Initial discovery sends only a DTLS handshake, no device token.
5. Choose **Pair using the remote control**.
6. Hold the **right round button directly above M3 for 3 seconds**, as illustrated by the official Gi app. Immediately submit the pairing form.
7. The integration registers a new random local token by following the app's initial read sequence. It does not ignite the fireplace.
8. Check that the official Kalfire app still works. Existing app access remained functional on the tested unit.

If pairing times out, reopen the physical pairing window and submit again. Do not unpair the official remote, reset the fireplace, change gas parameters or bridge safety contacts.

Tokens are stored in Home Assistant's config entry storage and are not exported in integration diagnostics. Treat Home Assistant backups as sensitive. The integration never uploads tokens, addresses, serials or captured traffic.

## On/off controls

In integration options, **Enable explicit on/off controls** creates a normal HA switch. It can ignite a gas fireplace; use it deliberately with someone present. Do not expose it to unattended ignition automations, generic state restoration or automatic fault resets. The physical remote remains available for control.

The on/off commands follow the normal Gi app interface (`syscmd mode=1` and `mode=0`). The fireplace executes its own startup sequence. Start is refused when an error is reported or the fireplace is not idle. Application commands are sent once; a missing response is reported as uncertain and is **never automatically retried**. A new poll after that only reads state.

**Validation:** normal start and stop through the HA switch have both been physically confirmed by the owner. HA subsequently reported `running` and `no_request`, with error code 0. During startup one read timed out and recovered automatically. Immediate post-command reads can briefly show the previous state; see [validation](docs/validation.md). These beta limitations remain under investigation.

## Transport security and limits

The tested device uses DTLS 1.2 and `ECDHE-ECDSA-AES256-GCM-SHA384`, with an X.509 certificate issued by a private iQontrol CA. This integration uses **explicit trust on first use and certificate pinning**, not public-CA or manufacturer-CA validation. A first connection on an untrusted network cannot establish the device's identity independently. A changed pin blocks application data; it is not silently accepted.

The client communicates directly with the fireplace. HA start/stop also worked under a temporary device-specific UniFi Internet-block rule. No independent WAN drop-counter/capture proof or cold-start/long-duration offline test was collected; see [validation](docs/validation.md). Firmware and protocol differences may require changes. Discovery scans, direct gas-valve writes, firmware flashing and error-reset commands are not implemented.

## Troubleshooting

- **Cannot connect:** verify IP, same subnet, signal strength and UDP 5684. Check the official app first.
- **Token rejected:** use the reauthentication flow and physical remote pairing. A cloud password is not a local token.
- **Certificate changed:** verify the device before removing/re-adding the integration to accept a new pin. Do not bypass the check.
- **Command outcome uncertain:** look at the fireplace and read its state before deciding on another action; do not automatically retry.
- **Entities unavailable:** no control or reconnect loop will restart the fireplace. The integration will retry read-only polling.
- **Need to remove:** delete the integration entry and uninstall through HACS. No network, firmware or safety configuration needs restoring. Token revocation on the fireplace has not been documented; deleting an HA entry removes the locally stored token, not necessarily the device-side registration.

## Development and reporting

See [protocol notes](docs/protocol.md), [validation](docs/validation.md) and [contributing](CONTRIBUTING.md). Report your Gi model, firmware and HA version. Never post tokens, raw packet captures, serial numbers, private IP/MAC addresses or full HA backups.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```

Tests use fake peers and Home Assistant fixtures; they never address a live fireplace. Hardware testing is a separate, explicit action. No APKs, decompiled application code, certificates, secrets or home-network captures are included in this repository.

## Roadmap

- Improve post-command state feedback and investigate the observed startup read timeout. HACS installation, sensors and supervised HA start/stop have been confirmed on Home Assistant Green.
- Validate more Gi models/firmwares, independently verify WAN blocking and test cold-start/long-duration offline behavior.
- Add HA controls for flame height (normal levels 1–5) and Spark (0–5), following the supervised setting probes documented in validation. These are not yet HA controls in this beta. Research mode, lights and moods separately.
- Consider HACS default-directory inclusion after broader testing. Core inclusion would also benefit from publishing the independent protocol client as a separate Python package.

## License

MIT for the original implementation in this repository. Product names identify interoperability targets; no vendor logos or application assets are redistributed.
