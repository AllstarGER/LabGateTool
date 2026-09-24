import os
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def get_project_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_bundle_dir():
    return os.path.abspath(getattr(sys, "_MEIPASS", get_project_dir()))


def get_executable_dir():
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return get_project_dir()


def _unique_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        if not path:
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(os.path.abspath(path))
    return unique


def get_external_search_dirs():
    cwd = os.path.abspath(os.getcwd())
    if is_frozen():
        exe_dir = get_executable_dir()
        return _unique_paths(
            [
                exe_dir,
                cwd,
                os.path.dirname(exe_dir),
                os.path.dirname(os.path.dirname(exe_dir)),
                get_project_dir(),
            ]
        )
    return _unique_paths([cwd, get_project_dir()])


def find_external_path(*parts):
    for base_dir in get_external_search_dirs():
        candidate = os.path.join(base_dir, *parts)
        if os.path.exists(candidate):
            return candidate
    return None


def get_preferred_external_dir():
    return get_executable_dir() if is_frozen() else os.path.abspath(os.getcwd())


def get_preferred_external_path(*parts):
    return os.path.join(get_preferred_external_dir(), *parts)


def get_resource_path(*parts):
    bundle_candidate = os.path.join(get_bundle_dir(), *parts)
    if os.path.exists(bundle_candidate):
        return bundle_candidate
    external_candidate = find_external_path(*parts)
    if external_candidate is not None:
        return external_candidate
    if is_frozen():
        return bundle_candidate
    return os.path.join(get_project_dir(), *parts)
