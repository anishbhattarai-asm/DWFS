import math
from types import SimpleNamespace


def settings(defaults, options, limits=None):
    unknown = sorted(set(options) - set(defaults))
    if unknown:
        raise TypeError("unknown option %s, valid options are %s"
                        % (", ".join(unknown), ", ".join(sorted(defaults))))
    cfg = SimpleNamespace(**{**defaults, **options})
    for key, (low, high) in (limits or {}).items():
        value = getattr(cfg, key)
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not number or not math.isfinite(value) or not low <= value <= high:
            if math.isinf(high):
                raise ValueError("%s must be a number of at least %g, got %r" % (key, low, value))
            raise ValueError("%s must be a number from %g to %g, got %r" % (key, low, high, value))
    return cfg
