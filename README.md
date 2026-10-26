# Kalfire Gi Local for Home Assistant

An independent Home Assistant integration for Kalfire **Gi** gas fireplaces using the local encrypted CoAP/DTLS interface. No Kalfire cloud account, MQTT broker, relay wiring or custom firmware is required by this integration.

**Validated on one Gi with communication-board firmware 0.7.11 and Home Assistant 2026.10.2–2026.10.4.** It is not a Kalfire product and is not endorsed by Kalfire or iQontrol. Other Kalfire product families, including older iMatch fireplaces, are not supported.

## Features

The integration includes its own local Kalfire app icon in `brand/icon.png` (supported by HA 2026.3+).


- Local temperature, operating state, error code and flame-height **setting** sensors.
- Firmware version in device information; the read-only flame-height setting is under Diagnostics, alongside optional raw status bits.
- Setup through **Settings → Devices & services → Add integration → Kalfire Gi Local**.
- Physical pairing with the official remote; alternatively import an existing local device token.
- Automatically remembered SHA256 certificate pin on first connection, checked on every subsequent connection.
- Automatic IP address recovery through Home Assistant DHCP discovery and the Gi's local discovery protocol. The stored certificate and device MAC are checked before accepting a new address.
- Optional normal on/off switch and flame-height slider (1–5), enabled through integration options. Burner controls are off by default; Ember Glow is always available.
- Optional Sparks slider (0–5); enable only if the generator is installed.
- Ember Glow slider with discrete levels 0–5, plus a separate Flicker switch (native level 6). Works while the gas fireplace is off. Available independently of the on/off control option.
- Ember Glow shows the active LED level. The steady-level slider is unavailable during flicker. Turning flicker off returns to the last observed steady level (default 3 after a restart if none was observed). Setup and polling never toggle the LEDs.
- Updating from beta 4 replaces the old percentage light entity with a number and switch. Update any dashboard cards or automations that referred to the old light.
- Flame-height and Sparks controls are available only while running without a reported fault. They never ignite the fireplace. Readback can lag an accepted command until a later poll.
- Address reconfiguration, reauthentication, redacted diagnostics and English, Dutch, German, French, Italian, Spanish, Portuguese, Polish, Czech, Danish and Swedish UI.

The flame-height sensor reports a stored setting, **not** proof of a flame. The state follows the device's own state machine. No ignition, reset or other control command is sent by setup, pairing, polling, reloading or reconnecting.

## Install with HACS

The repository can be used as a **custom repository**; inclusion in HACS's default directory is a separate future review.

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/buZybaZzz/home-assistant-kalfire-gi`, category **Integration**.
3. Download **Kalfire Gi Local**. Choose the latest stable release.
4. Restart Home Assistant once to load the custom integration.
5. Add **Kalfire Gi Local** under Devices & services.

Manual alternative: copy `custom_components/kalfire_gi/` into `/config/custom_components/kalfire_gi/` and restart Home Assistant. All runtime files are in that one directory. A separate compiled executable is not needed.

## Pair your fireplace

Keep the fireplace's official remote paired and in its normal location near the fireplace. The remote and the fireplace's existing safety functions remain necessary.

1. Put Home Assistant and the fireplace on the same trusted LAN/subnet for the initial setup. Allow unicast UDP 5684. Cross-subnet support has not been established; no broad firewall opening or port forwarding is needed.
2. Start adding the integration. It searches the local network for about five seconds and prefills a discovered address. If several fireplaces are found, choose an address from the list.
3. Confirm the address or enter an IP address or hostname manually if discovery finds nothing (for example, across VLANs). You can find the IP address in your router. The default port is 5684; a DHCP reservation is optional. Setup compares literal IPv4 addresses with the subnets of HA’s enabled interfaces and warns before connecting if none match. You can change the address or explicitly try anyway for routed/container networks. Hostnames and unavailable interface data cannot be checked this way.
4. Home Assistant automatically remembers the certificate from the selected address and continues to the pairing choices. Network discovery sends a local multicast query; checking the selected address sends only a DTLS handshake, no device token.
5. Choose **Pair using the remote control**.
6. Hold the **right round button directly above M3 for 3 seconds**, as illustrated by the official Gi app. Immediately submit the pairing form.
7. The integration registers a new random local token by following the app's initial read sequence. It does not ignite the fireplace.
8. Check that the official Kalfire app still works. Existing app access remained functional on the tested unit.

If pairing times out, reopen the physical pairing window and submit again. Do not unpair the official remote, reset the fireplace, change gas parameters or bridge safety contacts.

Tokens are stored in Home Assistant's config entry storage and are not exported in integration diagnostics. Treat Home Assistant backups as sensitive. The integration never uploads tokens, addresses, serials or captured traffic.

## On/off controls

In integration options, **Enable explicit on/off controls** creates a normal HA switch. It can ignite a gas fireplace; use it deliberately with someone present. Do not expose it to unattended ignition automations, generic state restoration or automatic fault resets. The physical remote remains available for control.

The on/off commands follow the normal Gi app interface (`syscmd mode=1` and `mode=0`). The fireplace executes its own startup sequence. Start is refused when an error is reported or the fireplace is not idle. Application commands are sent once; a missing response is reported as uncertain and is **never automatically retried**. A new poll after that only reads state.

**Validation:** normal start and stop through the HA switch have both been physically confirmed by the owner. HA subsequently reported `running` and `no_request`, with error code 0. During startup one read timed out and recovered automatically. Immediate post-command reads can briefly show the previous state; see [validation](docs/validation.md). The observed startup read timeout and delayed readback remain documented limitations.

## Transport security and limits

The tested device uses DTLS 1.2 and `ECDHE-ECDSA-AES256-GCM-SHA384`, with an X.509 certificate issued by a private iQontrol CA. This integration uses **automatic trust on first use and certificate pinning**, not public-CA or manufacturer-CA validation. A first connection on an untrusted network cannot establish the device's identity independently. A changed pin blocks application data; it is not silently accepted.

The client communicates directly with the fireplace. HA start/stop also worked under a temporary device-specific UniFi Internet-block rule. No independent WAN drop-counter/capture proof or cold-start/long-duration offline test was collected; see [validation](docs/validation.md). Firmware and protocol differences may require changes. Direct gas-valve writes, firmware flashing and error-reset commands are not implemented.

### Changing IP addresses

Home Assistant can update an already paired fireplace's address from DHCP discovery. If the configured address cannot be reached during startup or polling, the integration also sends `WHEREIS lanboard` to multicast group `239.10.11.13`, UDP port 3333, on HA's enabled IPv4 interfaces. It accepts only candidates that pass the existing certificate pin and return the paired device's MAC. Token, pairing, device and entity identities remain unchanged. Recovery only reads; it never replays a control command.

Fallback searches are shared between fireplaces, run only after a connection failure and are limited to once per minute per entry. Each interface listens for at most five seconds, with a bounded number of replies and identity checks. If discovery fails, the entities remain unavailable and later polls retry. A DHCP reservation remains optional.

Multicast discovery was confirmed from a Mac to one Gi with firmware 0.7.11. Automatic address recovery in both directions was also confirmed on HA Green after a real temporary DHCP address change, retaining the existing entry, device and ten entity IDs. The return was delayed during a weak Wi-Fi association; see [validation](docs/validation.md). Local discovery normally requires the same subnet and multicast access. An mDNS reflector alone does not forward this separate protocol. DHCP discovery can also receive address information through supported router device trackers, but visibility across VLANs depends on the network setup. If neither method finds the fireplace, use **Reconfigure** to enter its new address manually. A certificate or authentication error at the configured address does not trigger discovery or automatic pairing.

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

Tests use fake peers and Home Assistant fixtures; they never address a live fireplace. Hardware testing is a separate, explicit action. No APKs, decompiled application code, certificates, secrets or home-network captures are included. The sole vendor image is the app icon, shipped unmodified for product identification; see [asset notice](custom_components/kalfire_gi/brand/NOTICE.md).

## Roadmap

- Improve post-command state feedback and investigate the observed startup read timeout. HACS installation, sensors and supervised HA start/stop have been confirmed on Home Assistant Green.
- Validate more Gi models/firmwares, independently verify WAN blocking and test cold-start/long-duration offline behavior.
- Installed beta 2 flame-height, Spark and normal stop were physically confirmed by the owner. The owner confirmed Ember Glow on/off, brightness and native flicker. Research moods and native temperature modes next.
- Consider HACS default-directory inclusion after broader testing. Core inclusion would also benefit from publishing the independent protocol client as a separate Python package.

## License

MIT for the original implementation in this repository. Product names identify interoperability targets. The bundled Kalfire app icon remains third-party artwork, outside the MIT licence; see its [notice](custom_components/kalfire_gi/brand/NOTICE.md).
