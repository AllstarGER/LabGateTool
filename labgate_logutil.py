import sys

from loguru import logger


_configured = False


def log_config():
    """Configure only the local LabGate log sinks."""
    global _configured
    if _configured:
        return
    logger.remove()
    logger.add("log/log.log", rotation="3 MB", retention="3 days", level="INFO")
    stdout_sink = sys.stdout or sys.__stdout__
    if stdout_sink is not None:
        logger.add(stdout_sink, level="TRACE")
    _configured = True
