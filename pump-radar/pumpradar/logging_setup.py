import logging, sys
def setup_logging(verbose=False):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)-5s %(name)-18s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout, force=True)
    for n in ("websockets",): logging.getLogger(n).setLevel(logging.WARNING)
