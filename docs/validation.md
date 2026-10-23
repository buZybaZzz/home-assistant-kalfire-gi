# Validation record

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
