ocs/protocol.md# Gi local protocol observations

These notes document observed interoperability, not a supported vendor API contract.

- Transport: unicast IPv4 UDP 5684, CoAP over DTLS 1.2.
- Tested cipher: ECDHE-ECDSA-AES256-GCM-SHA384. No client certificate was needed on the tested unit.
- CoAP: confirmable PUT to case-sensitive `Json`, Uri-Query `token=<24 lowercase hex characters>`.
- Content-Format/Accept omitted, matching the observed app implementation.
- JSON reads: `{"id":123,"method":"rget","params":{"name":"modbus.1100"}}`.
- JSON result: `{"id":123,"result":{"name":"modbus.1100","value":207}}`.
- Temperature scale: value / 10 = degrees Celsius. The inspected Android app truncates to a whole number for display.
- Unpaired token: CoAP 4.01. Paired read: CoAP 2.05.
- Normal start: `{"id":123,"method":"syscmd","params":{"mode":1}}`.
- Normal stop: same method with mode 0 (app-derived; not physically validated yet).
- Command acknowledgement: `{"id":123,"result":"success"}`. This does not prove a flame or completed startup; observe device state and physical outcome.

| Read field | Meaning |
|---|---|
| `sys.info.bmac` | Device MAC; used for stable HA identity |
| `sys.info.bsn` | Serial; only used to follow the initial pairing sequence, not stored |
| `sys.info.bsv` | Communication-board firmware |
| `modbus.1100` | Temperature, tenths of a degree |
| `modbus.1106` | Status bitfield (semantics not fully established) |
| `modbus.1107` | Error code |
| `modbus.1111` | Operating state |
| `sys.control.flame_height` | Flame-height setting; no flame-detection claim |

State codes from the Gi app: 0 noRequest, 1 waiting, 2 safety, 3 purge, 4 startup, 5 running, 6 lockout, 7 eMode. Unknown values are not interpreted as safe/running.

The app generates a local token on a new pairing, retains it in device preferences and includes it in each request. During the physically opened pairing window the initial serial/MAC read sequence registered a new random token on the tested unit. Existing official app operation remained intact. Token capacity and revocation are unknown; avoid repeatedly creating unnecessary pairings.

The implementation intentionally contains no generic write-register action, no gas-valve writes, no firmware commands and no reset action. A switch action does not directly drive gas valves.

Sources used for interoperability research:

- [Kalfire Gi user manual](https://kalfire.com/downloads/Handleidingen/Gashaarden/Gi/User%20manual%20Kalfire%20Gi_NL_V06_2026.pdf)
- [Kalfire Gi installation manual](https://kalfire.com/downloads/Handleidingen/Gashaarden/Gi/Installation%20instruction%20Kalfire%20Gi_NL.pdf)
- [Official Android app listing](https://play.google.com/store/apps/details?id=com.iqontrol.GPXApp)
- [CoAP RFC 7252](https://www.rfc-editor.org/rfc/rfc7252)
- [pyOpenSSL](https://pyopenssl.org/en/stable/api/ssl.html)

The inspected Android package was version 1.0.42, obtained through a distribution mirror. Its signing identity was not independently compared against a Google Play download. It was not executed. Static observations were followed by successful local reads and one explicit, supervised physical start test. This repository contains an original implementation of those observed messages, not the vendor application or its disassembly.
