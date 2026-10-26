"""Typed errors; messages never include credentials or raw responses."""


class KalfireError(Exception):
    """Base protocol/transport error."""


class CannotConnect(KalfireError):
    """Peer unavailable or secure session could not be established."""


class AuthenticationError(KalfireError):
    """The local device token is not paired."""


class CertificateChanged(KalfireError):
    """Peer certificate differs from the saved pin."""


class ProtocolError(KalfireError):
    """Malformed or unexpected peer response."""


class CommandUncertain(KalfireError):
    """A command may have been delivered; never retry it automatically."""
