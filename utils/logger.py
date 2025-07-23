import logging
import sys

def get_logger(name: str = "pdf_to_anki") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers in Jupyter / reruns
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger