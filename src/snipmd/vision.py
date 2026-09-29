"""Apple Vision text recognition, the fast path for plain text mode.

Uses VNRecognizeTextRequest through pyobjc. No model download, runs on the
Neural Engine, and returns in a fraction of a second. It does not understand
math or tables, which is why the other modes go to GLM-OCR.
"""

from __future__ import annotations

import sys
from pathlib import Path


class VisionUnavailable(RuntimeError):
    pass


def available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


def _group_lines(items: list[tuple[float, float, float, str]]) -> list[str]:
    """Order boxes top to bottom, then left to right, merging boxes on one line.

    Each item is (top, left, height, text) with top measured from the top edge
    in normalised coordinates.
    """
    items = sorted(items, key=lambda t: (t[0], t[1]))
    lines: list[list[tuple[float, float, float, str]]] = []
    for item in items:
        if lines:
            last = lines[-1]
            ref_top, ref_h = last[0][0], last[0][2]
            if abs(item[0] - ref_top) < max(ref_h, item[2]) * 0.5:
                last.append(item)
                continue
        lines.append([item])
    return [" ".join(t[3] for t in sorted(line, key=lambda t: t[1])) for line in lines]


def recognize(image: Path, languages: list[str] | None = None) -> str:
    if not available():
        raise VisionUnavailable("Apple Vision needs macOS with pyobjc-framework-Vision installed")
    import Vision
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(image))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    if languages:
        request.setRecognitionLanguages_(languages)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise VisionUnavailable(f"Vision request failed: {error}")
    items = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        box = obs.boundingBox()
        top = 1.0 - (box.origin.y + box.size.height)
        items.append((top, box.origin.x, box.size.height, str(candidates[0].string())))
    return "\n".join(_group_lines(items))
