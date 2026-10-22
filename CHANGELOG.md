# Changelog

## 0.1.0b1 — initial local beta

- Original async local CoAP/DTLS client using pyOpenSSL; no compiled helper or cloud login.
- Explicit certificate trust, physical pairing and existing-token import.
- Local temperature, state, error code and flame-height-setting sensors; firmware in device information.
- Optional explicit normal on/off switch; no controls by default.
- Reauthentication, address reconfiguration, private diagnostics and English/Dutch UI.
- 44 offline tests against Home Assistant 2026.10.2; local hassfest, Ruff and formatting checks pass.
- Live Python reads and one supervised normal start validated on a Gi with firmware 0.7.11.

The normal stop command and installed HA Green runtime still need hardware validation. This is an early beta for one tested firmware, not a claim of universal model support or HACS default-directory inclusion.
