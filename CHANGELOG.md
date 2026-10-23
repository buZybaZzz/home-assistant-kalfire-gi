# Changelog

## 0.1.0b2 — normal level controls

- Add flame-height (1–5) and optional Natural Spark (0–5) number entities.
- Spark is explicitly opted into for units with the optional generator.
- Permit only the two named normal settings, with fresh running/fault checks and no command retries or value restoration.
- Show device readback rather than optimistically accepting the requested setting.
- 62 offline tests pass, including real Home Assistant service calls, delayed readback, unavailable devices, exact write format and timeout handling.
- Prior supervised hardware tests confirmed both flame-height changes and Spark 5; installed beta 2 controls still require runtime validation.
- Normal HA start and stop were physically validated, also under a configured fireplace-only UniFi Internet block.


## 0.1.0b1 — initial local beta

- Original async local CoAP/DTLS client using pyOpenSSL; no compiled helper or cloud login.
- Explicit certificate trust, physical pairing and existing-token import.
- Local temperature, state, error code and flame-height-setting sensors; firmware in device information.
- Optional explicit normal on/off switch; no controls by default.
- Reauthentication, address reconfiguration, private diagnostics and English/Dutch UI.
- 44 offline tests against Home Assistant 2026.10.2; local hassfest, Ruff and formatting checks pass.
- Live Python reads and one supervised normal start validated on a Gi with firmware 0.7.11.

Historical initial-beta limitation (subsequently validated): the normal stop command and installed HA Green runtime needed hardware validation. This is an early beta for one tested firmware, not a claim of universal model support or HACS default-directory inclusion.
