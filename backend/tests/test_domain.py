import pytest

from app.domain.errors import InvalidAlias, InvalidTarget, InvalidTransition, PortRangeExhausted
from app.domain.models import Redirect, RedirectStatus, normalize_alias, parse_target
from app.services.port_allocator import PortAllocator


@pytest.mark.parametrize(
    ("raw", "host", "port", "is_domain"),
    [
        ("1.2.3.4", "1.2.3.4", None, False),
        ("1.2.3.4:9988", "1.2.3.4", 9988, False),
        (" ts.Ejemplo.com ", "ts.ejemplo.com", None, True),
        ("ts.ejemplo.com:10011", "ts.ejemplo.com", 10011, True),
        ("2001:db8::1", "2001:db8::1", None, False),
        ("[2001:db8::1]:9987", "2001:db8::1", 9987, False),
    ],
)
def test_parse_target_valid(raw, host, port, is_domain):
    t = parse_target(raw)
    assert (t.host, t.port, t.is_domain) == (host, port, is_domain)


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "1.2.3.4:0", "1.2.3.4:70000", "host:abc", "localhost", "ts3server://a.com",
     "a b.com", "0.0.0.0", "-bad-.com", "999.1.1.1"],
)
def test_parse_target_invalid(raw):
    with pytest.raises(InvalidTarget):
        parse_target(raw)


def _redirect(status=RedirectStatus.PENDING) -> Redirect:
    return Redirect("a", "a", None, False, "1.1.1.1", 9987, 10000, status=status)


def test_state_transitions():
    r = _redirect()
    r.transition_to(RedirectStatus.ERROR, "fallo")
    assert r.error == "fallo"
    r.transition_to(RedirectStatus.ACTIVE)
    assert r.error is None
    r.transition_to(RedirectStatus.STOPPED)
    with pytest.raises(InvalidTransition):
        r.transition_to(RedirectStatus.ACTIVE)


def test_port_allocator():
    alloc = PortAllocator(range(100, 103))
    assert alloc.choose(set()) == 100
    assert alloc.choose({100, 102}) == 101
    with pytest.raises(PortRangeExhausted):
        alloc.choose({100, 101, 102})
    usage = alloc.usage({100, 101, 5000})
    assert (usage.used, usage.total, usage.free) == (2, 3, 1)


def test_normalize_alias():
    assert normalize_alias("  Clan \t Paletas\n") == "Clan Paletas"
    assert normalize_alias("Ñandú 🎮") == "Ñandú 🎮"
    assert normalize_alias("x" * 60) == "x" * 60
    for bad in ("", "   ", "x" * 61):
        with pytest.raises(InvalidAlias):
            normalize_alias(bad)
