# Security

A paired local token permits access to a gas appliance. Keep it private and protect Home Assistant and its backups. The initial certificate is remembered automatically during setup on a trusted local network. This first connection does not independently authenticate the fireplace through a manufacturer CA. Every subsequent connection checks the saved certificate pin; a changed certificate blocks application data.

Report a suspected secret exposure or security issue privately through GitHub's security reporting if available, or contact the repository maintainer through their GitHub profile. Do not post real tokens, addresses, serials or packet captures publicly.

This early beta is intended for supervised testing. The physical appliance's safety controls remain required. Network presence, a successful CoAP response and a saved flame-height setting are not independent proof of a safe flame.
