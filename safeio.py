import builtins


_ORIGINAL_PRINT = builtins.print


def safe_print(*args, **kwargs):
    try:
        _ORIGINAL_PRINT(*args, **kwargs)
    except OSError:
        # Some Windows GUI runs may have no valid stdout handle.
        return


def install_safe_print():
    if builtins.print is not safe_print:
        builtins.print = safe_print
