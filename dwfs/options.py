from types import SimpleNamespace


def settings(defaults, options):
    unknown = sorted(set(options) - set(defaults))
    if unknown:
        raise TypeError("unknown option %s, valid options are %s"
                        % (", ".join(unknown), ", ".join(sorted(defaults))))
    return SimpleNamespace(**{**defaults, **options})
