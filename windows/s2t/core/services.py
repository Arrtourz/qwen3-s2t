from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np


class HotkeyService(ABC):
    @abstractmethod
    def register(self, hotkey: str, callback) -> None:
        raise NotImplementedError

    @abstractmethod
    def unregister(self) -> None:
        raise NotImplementedError


class AudioCaptureService(ABC):
    @abstractmethod
    def start_recording(self, windowed: bool) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop_recording(self) -> np.ndarray | None:
        raise NotImplementedError

    @abstractmethod
    def snapshot_recording(self) -> np.ndarray | None:
        raise NotImplementedError

    @abstractmethod
    def is_recording(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class PasteService(ABC):
    @abstractmethod
    def paste_text(self, text: str) -> None:
        raise NotImplementedError


class TrayService(ABC):
    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify(self, title: str, message: str) -> None:
        raise NotImplementedError
