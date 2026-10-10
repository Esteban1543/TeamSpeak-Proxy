"""Errores del dominio. No dependen de HTTP; la capa API los traduce."""


class DomainError(Exception):
    """Error base del dominio."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidTarget(DomainError):
    """El destino introducido no tiene un formato válido."""


class ResolveError(DomainError):
    """No se pudo resolver el dominio a una IP/puerto."""


class PortRangeExhausted(DomainError):
    """No quedan puertos libres en el rango configurado."""


class RedirectNotFound(DomainError):
    """La redirección no existe."""


class InvalidTransition(DomainError):
    """Transición de estado no permitida."""


class EngineError(DomainError):
    """El motor de reenvío no pudo arrancar o detener un proxy."""
