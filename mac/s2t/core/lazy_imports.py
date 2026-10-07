from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import types


log = logging.getLogger(__name__)

# `import qwen_asr` runs the package __init__, which exports Qwen3ForcedAligner
# (-> nagisa) and pulls inference/utils.py (-> librosa, soundfile). None of them
# are reachable from this app: librosa/soundfile only handle file paths and
# resampling of audio whose rate is not 16kHz, nagisa only tokenizes Japanese for
# the forced aligner, and we always hand the model a 16kHz numpy array. Importing
# them anyway costs ~290MB of RSS and ~0.9s of startup (they drag in numba,
# llvmlite, scikit-learn and pandas), so they are replaced with proxies that
# import the real module on first attribute access. Nothing is lost if some code
# path does reach them — it just pays the import then.
DEFERRED_MODULES = ("librosa", "soundfile", "nagisa")


class _LazyModule(types.ModuleType):
    """Stands in for a module until something actually touches its contents."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        # A real spec matters: transformers probes optional deps with
        # importlib.util.find_spec(), which raises ValueError on a None spec.
        self.__spec__ = importlib.util.spec_from_loader(name, loader=None)
        self._real: types.ModuleType | None = None

    def __getattr__(self, item: str) -> object:
        # Import machinery and introspection poke at dunders; answering those
        # with a real import would defeat the point.
        if item.startswith("__") and item.endswith("__"):
            raise AttributeError(item)
        if self._real is None:
            log.debug("Lazy module %s touched via .%s; importing for real", self.__name__, item)
            # Step out of sys.modules so import_module does real work rather than
            # handing back this proxy, and step back in if the import fails, so a
            # genuinely missing module stays a proxy instead of a hole.
            sys.modules.pop(self.__name__, None)
            try:
                self._real = importlib.import_module(self.__name__)
            except BaseException:
                sys.modules.setdefault(self.__name__, self)
                raise
            sys.modules[self.__name__] = self._real
        return getattr(self._real, item)


def defer_unused_imports(names: tuple[str, ...] = DEFERRED_MODULES) -> None:
    """Install lazy proxies for `names`, skipping any already imported."""
    for name in names:
        if name not in sys.modules:
            sys.modules[name] = _LazyModule(name)


# transformers resolves optional integrations at import time, then eagerly
# imports them from modules that load alongside any model. Each entry here is a
# transformers availability flag whose only consumers are features this app does
# not use, plus the reason, so the next person can re-check the claim:
#
#   sklearn: generation/candidate_generator.py imports sklearn.metrics.roc_curve
#     to tune the acceptance threshold for assisted (speculative) decoding, which
#     requires a second draft model. We never pass one. Pulls in pandas too.
#   scipy: loss/loss_for_object_detection.py imports scipy.optimize for DETR-style
#     Hungarian matching. Every scipy consumer in transformers is vision, protein
#     folding or pop2piano — none are audio or ASR.
#
# transformers guards both with its own is_*_available() checks, so clearing the
# flags makes it take the already-supported "not installed" path.
_UNUSED_TRANSFORMERS_INTEGRATIONS = ("sklearn", "scipy")


def disable_unused_transformers_integrations(
    names: tuple[str, ...] = _UNUSED_TRANSFORMERS_INTEGRATIONS,
) -> list[str]:
    """Clear transformers' availability flags for integrations we never use.

    Saves ~110MB of RSS at model load (~70MB sklearn + pandas, ~40MB scipy).
    Returns the flags actually cleared.
    Best-effort: a transformers version that renames or drops a flag just keeps
    the corresponding dependency.
    """
    cleared: list[str] = []
    try:
        from transformers.utils import import_utils
    except Exception:
        log.debug("Could not reach transformers.utils.import_utils", exc_info=True)
        return cleared

    for name in names:
        attr = f"_{name}_available"
        try:
            if getattr(import_utils, attr, False):
                setattr(import_utils, attr, False)
                cleared.append(name)
        except Exception:
            log.debug("Could not clear transformers flag %s", attr, exc_info=True)
    if cleared:
        log.debug("Skipping unused transformers integrations: %s", ", ".join(cleared))
    return cleared
