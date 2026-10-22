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

## Still needs validation

- Physical normal stop. It was not tested because the owner asked to leave the fireplace on.
- HA installation/runtime and HACS download on the Green.
- Other Gi models/firmwares, power-loss recovery and internet-loss behavior.
- Pairing-token limits/revocation and device certificate rotation behavior.
- Additional settings such as mode, lights and moods.

Automated tests exercise the real Home Assistant package with mocked device communication. They do not prove gas-appliance behavior on other hardware. See GitHub Actions for code checks; release notes must not describe an unperformed hardware test as completed.

## Local software validation

44 offline tests passed against the actual Home Assistant 2026.10.2 Python package. Ruff lint/format checks passed. Official hassfest from tag 2026.10.2 reported 1 integration, 0 invalid integrations. The final Python read-only check on the running fireplace succeeded. GitHub-hosted CI and HACS retrieval have not yet been run; those require a published repository.
