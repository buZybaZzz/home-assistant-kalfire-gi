# Validation record

## Automatic address recovery, 26 October 2026

The new recovery implementation was exercised from a Mac using HA's network interface detection, an intentionally obsolete address in a temporary test configuration, and the existing device pin and token. It discovered the paired Gi at its actual address, verified its certificate and MAC, and read firmware 0.7.11, state 0 and error code 0. Only discovery and reads were sent; the production HA and network configuration were not changed.

104 offline tests pass, including startup/polling recovery, unchanged device/entity registry IDs, verified DHCP updates and reloads, rejected candidates, bounded retries/timeouts, cancellation and client cleanup. Ruff and hassfest pass. The implementation was subsequently installed on HA Green with Core 2026.10.4. A real, temporary UniFi DHCP reservation and targeted Wi-Fi reconnect moved the Gi to a different address; an independent discovery reply confirmed that address and HA updated its saved host automatically. The existing entry, device and all ten entity IDs were retained. The return to the original address was delayed while the fireplace associated with a weak access point (-83 to -84 dBm). It later returned to the original AP (-60 dBm), and HA automatically saved the original host and resumed reads (idle/no_request, error 0). The temporary DHCP reservation was removed; no AP lock was applied and no appliance controls were sent. DHCP and multicast were not isolated in these hardware tests, including the return during a normal Core restart. Cross-VLAN recovery and every firmware's discovery reply format remain unverified.

Hardware observations: 22 October 2026, one Kalfire Gi, communication-board firmware 0.7.11. Exact Gi size/model was not established. Home Assistant Green: Core 2026.10.2, OS 18.3.

## Confirmed on the live fireplace

- Encrypted local DTLS session; certificate pin checked before token transmission.
- Unpaired read rejected with 4.01.
- Physical remote pairing followed by successful serial/MAC identity reads.
- Existing official phone app remained functional, confirmed by the owner.
- Firmware, temperature, status, error and state reads after reconnecting.
- Python transport reads while the fireplace was running, without a compiled helper.
- One explicitly authorized normal start, from idle/error 0: success response, state sequence safety → startup → running, error 0; owner confirmed visible flames.
- No automatic retries, safety-contact changes, fault resets, firmware changes or direct gas-valve writes.
- HA installation check, 23 October 2026: HACS downloaded `v0.1.0b1` on Home Assistant Green. After a normal HA restart, setup imported the existing local token and checked the same certificate fingerprint.
- Live HA device page displayed firmware 0.7.11, temperature 20.0 degrees Celsius, state `no_request` (Dutch: Geen aanvraag), flame-height setting 0 and error code 0. The owner had independently switched the fireplace off before this check. Controls remained disabled; setup and polling sent no ignition or stop command.

## Still needs validation

- Other Gi models/firmwares, power-loss recovery and internet-loss behavior.
- Pairing-token limits/revocation and device certificate rotation behavior.
- Additional settings such as mode, lights and moods.

Automated tests exercise the real Home Assistant package with mocked device communication. They do not prove gas-appliance behavior on other hardware. See GitHub Actions for code checks; release notes must not describe an unperformed hardware test as completed.

## Supervised HA control test, 23 October 2026

Controls were explicitly enabled for a supervised test. One HA start command produced visible flames, confirmed by the owner; the eventual state was `running`, error 0. One HA stop command extinguished the flames, confirmed by the owner; subsequent polling returned `no_request`, error 0. No command was automatically repeated. Reloading the integration afterwards restored sensors and the off switch state without igniting the fireplace.

Two beta limitations were observed: the immediate post-command read can still return the previous state (making the switch briefly appear to revert), and one local request timed out during startup. The entities became unavailable, then recovered automatically on subsequent read-only polling and reported startup/running. The cause of the timeout is not established; this test does not prove continuous connection reliability. Diagnostics after stop reported successful polling, state 0, error 0 and flame-height setting 0. The exported integration data contained no device token, host, MAC, serial or certificate fingerprint.

## Local software validation

44 offline tests passed against the actual Home Assistant 2026.10.2 Python package. Ruff lint/format checks passed. Official hassfest from tag 2026.10.2 reported 1 integration, 0 invalid integrations. The final Python read-only check on the running fireplace succeeded.

GitHub-hosted [Checks run 4](https://github.com/buZybaZzz/home-assistant-kalfire-gi/actions/runs/39844170683), commit `1b8e325`, passed all three jobs: tests (including Ruff), current hassfest and HACS validation. HACS download and live HA sensor operation on the Green were subsequently confirmed as described above. The manifest relies on pyOpenSSL supplied by Home Assistant itself, as required by the current hassfest validator.

## Targeted WAN and setting tests, 23 October 2026

A temporary UniFi rule blocked Internet for only the verified fireplace client while preserving LAN access. With that rule active, one HA start and one HA stop both worked physically, confirmed by the owner. HA subsequently reported running/no_request and error 0. The same recoverable startup read timeout occurred. The temporary rule was then paused (UniFi displayed Resume), restoring the prior Internet policy. No independent WAN packet capture/drop-counter verification was collected: this establishes behavior under the configured Internet-block policy, not cold-start or long-duration WAN independence. Gateway-provided DNS/NTP were not separately blocked.

With the normal Internet policy restored, a supervised probe used the same pinned DTLS transport and normal app `rset` messages (`type: integer`). Setting `sys.control.flame_height` to 2 succeeded, read back 2 and visibly changed flame height, confirmed by the owner. Setting `modbus.2007` (Spark) to 2 succeeded and eventually read back 2; the first read still returned 0. These settings are not yet exposed as HA controls in this beta. Only named ordinary settings were touched; no generic register service or safety/reset command was added.

Cleanup of the setting probe: Spark was restored to 0 and read back 0. Restoring the initial flame-height status value 0 was rejected with protocol error -31001; documented normal level 1 was then accepted and read back 1. This demonstrates that the readable initial 0 is not a writable normal flame-height setting. The fireplace remained state 5/error 0 during the probe, then a normal HA stop was sent. No extra HA setting controls have yet been installed.

## Repeated Spark observation, 23 October 2026

The first Spark probe had no physical confirmation because the owner was on the phone. The supervised test was repeated: after the device reported running/error 0, Spark 2 was accepted and subsequently read back 2. At the owner's request flame height was raised to 3 (accepted/read back 3), then Spark to its normal app maximum 5 (accepted, delayed readback 5). The owner explicitly confirmed visible sparks. Final observation: state 5, error 0, flame-height setting 3, Spark 5. The fireplace and settings were left running for the present owner; no further stop command was sent. This confirms these specific settings on the tested unit, not every value on every model.
