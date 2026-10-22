# Contributing

Use Python 3.14.2 or newer and install `requirements-dev.txt`. Run Ruff and pytest before opening a pull request. Include a regression test for protocol parsing, config-flow or command-delivery changes.

The protocol client lives in `custom_components/kalfire_gi/gi/` and has no Home Assistant dependency. Keep HA-specific code outside it. Keep all runtime files beneath this integration directory for HACS installation.

All automated tests must remain offline. Never add a live address or secret to a test fixture. Hardware tests require an explicit request from someone physically present. Do not add automatic ignition, start replay, automatic reset, generic register writes or safety bypasses.

Issues should contain model, communication-board firmware, HA version, the failed operation and a redacted error. No device tokens, full packet captures, serials or backups. The included diagnostics omit connection credentials and device addresses.

No vendor binaries, disassembly, graphics or manual scans belong in this repository. Add original code and concise interoperability observations with links to public sources.
