from __future__ import annotations

from dataclasses import replace
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ...core.config import AppConfig, ConfigError, save_config


class SettingsWindow:
    def __init__(self, config: AppConfig, config_path, on_saved) -> None:
        self._config = config
        self._config_path = config_path
        self._on_saved = on_saved
        self._thread = None
        self._lock = threading.Lock()

    def show(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run_window, daemon=True)
            self._thread.start()

    def _run_window(self) -> None:
        root = tk.Tk()
        root.title("s2t Settings")
        root.geometry("420x260")
        root.resizable(False, False)
        root.columnconfigure(1, weight=1)

        hotkey_var = tk.StringVar(value=self._config.hotkey)
        mode_var = tk.StringVar(value=self._config.recording.mode)
        model_var = tk.StringVar(value=self._config.model.variant or "0.6b")
        device_var = tk.StringVar(value=self._config.model.device)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Hotkey").grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(frame, textvariable=hotkey_var).grid(row=0, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Mode").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=mode_var,
            values=["continuous", "manual"],
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Model").grid(row=2, column=0, sticky="w", pady=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=model_var,
            values=["0.6b", "1.7b"],
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Device").grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=device_var,
            values=["auto", "cpu", "gpu"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(
            frame,
            text="Use double_ctrl or a combo like ctrl+alt+h.",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))

        ttk.Button(button_row, text="Cancel", command=root.destroy).pack(side="right", padx=(10, 0))
        ttk.Button(
            button_row,
            text="Save",
            command=lambda: self._save_and_close(
                root=root,
                hotkey=hotkey_var.get().strip(),
                mode=mode_var.get().strip(),
                model_variant=model_var.get().strip(),
                device=device_var.get().strip(),
            ),
        ).pack(side="right")

        root.mainloop()

    def _save_and_close(
        self,
        *,
        root: tk.Tk,
        hotkey: str,
        mode: str,
        model_variant: str,
        device: str,
    ) -> None:
        variant_to_model_id = {
            "0.6b": "Qwen/Qwen3-ASR-0.6B",
            "1.7b": "Qwen/Qwen3-ASR-1.7B",
        }
        updated = replace(
            self._config,
            hotkey=hotkey,
            model=replace(
                self._config.model,
                variant=model_variant,
                path_or_id=variant_to_model_id[model_variant],
                device=device,
            ),
            recording=replace(
                self._config.recording,
                mode=mode,
            ),
        )
        try:
            save_config(updated, self._config_path)
            self._on_saved()
            root.destroy()
        except ConfigError as exc:
            messagebox.showerror("s2t config error", str(exc))
        except Exception as exc:
            messagebox.showerror("s2t save failed", str(exc))
