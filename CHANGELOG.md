# Changelog

## 0.1.2 — HACS default submission preparation

- Run HACS validation without ignored checks, including local brand assets.
- Clarify installation instructions to use the latest stable release. No device control or protocol changes.

## 0.1.1 — independent Ember Glow controls

- Always expose and poll Ember Glow brightness and Flicker, independently of burner controls. Remove the Ember Glow option; existing disabled settings no longer hide LED controls.

## 0.1.0 — first stable release

- Include the original Kalfire Connected app icon as a local HA brand image, with third-party provenance and licence notice.
- Rename the Dutch Haardstatus sensor to Status without changing its identity or history.
- Add complete German, French, Italian, Spanish, Portuguese, Polish, Czech, Danish and Swedish UI translations, alongside English and Dutch.
- Clarify control options: flame height and Sparks require the burner to run; Ember Glow also works with the gas burner off.
- Promote the physically validated beta feature set to the first stable release; no protocol or control changes. Startup read timeouts and delayed readback remain documented limitations on the tested firmware.


## 0.1.0b6 — clearer Dutch status label

- Rename the Dutch operating-state sensor from Toestand to Haardstatus. Existing entity ID, history and behavior are retained.


## 0.1.0b5 — discrete Ember Glow controls

- Replace the percentage light with a 0–5 slider and separate Flicker switch. The slider is unavailable during flicker; switching flicker off returns to the last observed steady level (fallback 3).
- Rename Spark to Sparks without changing existing entity IDs.
- Remove only the former integration-owned Ember Glow light registry entry during setup, without issuing device commands. Update dashboard cards/automations that referred to that light.
- Owner confirmed physical Ember Glow brightness changes and native flicker in beta 4.
- 78 offline tests cover migration, discrete service calls, flicker readback, return to the prior steady level, and no ignition.


## 0.1.0b4 — Ember Glow lighting

- Add an opt-in Ember Glow light with five steady brightness levels and native Flicker effect. LED-only operation works while the gas burner is off.
- Read active LED level separately from stored brightness. Never optimistically report an accepted request as the new light state.
- Use the normal app LED-only standby toggle when necessary; never send a gas start command, restore a light state, or retry a toggle.
- Local probes confirmed stored/active levels 3 and 6, with gas state 0 and error code 0. Physical observation and installed HA light control validation remain separate.
- 78 offline tests pass, including idle light service calls without gas ignition and uncertain-toggle handling.


## 0.1.0b3 — clearer device layout

- Move the read-only flame-height setting sensor to Diagnostics, keeping the number control under Controls. Existing entity IDs and stored setting values are retained.
- Owner confirmed installed beta 2 flame-height and Spark controls work correctly, and normal stop through HA extinguished the fireplace.


## 0.1.0b2 — normal level controls

- Add flame-height (1–5) and optional Natural Spark (0–5) number entities.
- Spark is explicitly opted into for units with the optional generator.
- Permit only the two named normal settings, with fresh running/fault checks and no command retries or value restoration.
- Show device readback rather than optimistically accepting the requested setting.
- 62 offline tests pass, including real Home Assistant service calls, delayed readback, unavailable devices, exact write format and timeout handling.
- Prior supervised hardware tests confirmed both flame-height changes and Spark 5; installed beta 2 controls were subsequently physically validated by the owner.
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
