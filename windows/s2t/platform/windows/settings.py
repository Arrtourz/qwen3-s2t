from __future__ import annotations

from dataclasses import replace
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ...core.config import (
    AppConfig,
    ConfigError,
    default_lightweight_binary_path,
    default_lightweight_model_dir,
    save_config,
)


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
        root.geometry("560x360")
        root.resizable(False, False)
        root.columnconfigure(1, weight=1)

        backend_var = tk.StringVar(value=_provider_to_ui_value(self._config.model.provider))
        hotkey_var = tk.StringVar(value=self._config.hotkey)
        mode_var = tk.StringVar(value=self._config.recording.mode)
        model_var = tk.StringVar(value=self._config.model.variant or "0.6b")
        device_var = tk.StringVar(value=self._config.model.device)
        binary_path_var = tk.StringVar(value=self._config.model.binary_path)
        model_dir_var = tk.StringVar(
            value=(
                self._config.model.path_or_id
                if self._config.model.provider == "qwen_asr_cli"
                else str(default_lightweight_model_dir(self._config.model.variant or "0.6b"))
            )
        )

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Backend").grid(row=0, column=0, sticky="w", pady=(0, 10))
        backend_combo = ttk.Combobox(
            frame,
            textvariable=backend_var,
            values=["python", "lightweight"],
            state="readonly",
        )
        backend_combo.grid(row=0, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Hotkey").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(frame, textvariable=hotkey_var).grid(row=1, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Mode").grid(row=2, column=0, sticky="w", pady=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=mode_var,
            values=["continuous", "manual"],
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Model").grid(row=3, column=0, sticky="w", pady=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=model_var,
            values=["0.6b", "1.7b"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Device").grid(row=4, column=0, sticky="w", pady=(0, 10))
        device_combo = ttk.Combobox(
            frame,
            textvariable=device_var,
            values=["auto", "cpu", "gpu"],
            state="readonly",
        )
        device_combo.grid(row=4, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="CLI Binary").grid(row=5, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(frame, textvariable=binary_path_var).grid(row=5, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="CLI Model Dir").grid(row=6, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(frame, textvariable=model_dir_var).grid(row=6, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(
            frame,
            text="Use ctrl+alt+h or a special value like double_ctrl. Lightweight backend uses qwen-asr and is CPU-only.",
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=8, column=0, columnspan=2, sticky="e", pady=(16, 0))

        ttk.Button(button_row, text="Cancel", command=root.destroy).pack(side="right", padx=(10, 0))
        ttk.Button(
            button_row,
            text="Save",
            command=lambda: self._save_and_close(
                root=root,
                provider_ui=backend_var.get().strip(),
                hotkey=hotkey_var.get().strip(),
                mode=mode_var.get().strip(),
                model_variant=model_var.get().strip(),
                device=device_var.get().strip(),
                binary_path=binary_path_var.get().strip(),
                model_dir=model_dir_var.get().strip(),
            ),
        ).pack(side="right")

        def _update_backend_fields(*_args) -> None:
            if backend_var.get() == "lightweight":
                device_combo.configure(values=["auto", "cpu"])
                if device_var.get() == "gpu":
                    device_var.set("auto")
                if not binary_path_var.get().strip():
                    binary_path_var.set(str(default_lightweight_binary_path()))
                if not model_dir_var.get().strip() or model_dir_var.get().strip().startswith("Qwen/"):
                    model_dir_var.set(str(default_lightweight_model_dir(model_var.get().strip() or "0.6b")))
            else:
                device_combo.configure(values=["auto", "cpu", "gpu"])

        def _update_model_dir(*_args) -> None:
            if backend_var.get() != "lightweight":
                return
            current_model_dir = model_dir_var.get().strip()
            suggested_prefix = str(default_lightweight_model_dir("0.6b").parent)
            if not current_model_dir or current_model_dir.startswith(suggested_prefix):
                model_dir_var.set(str(default_lightweight_model_dir(model_var.get().strip() or "0.6b")))

        backend_var.trace_add("write", _update_backend_fields)
        model_var.trace_add("write", _update_model_dir)
        _update_backend_fields()

        root.mainloop()

    def _save_and_close(
        self,
        *,
        root: tk.Tk,
        provider_ui: str,
        hotkey: str,
        mode: str,
        model_variant: str,
        device: str,
        binary_path: str,
        model_dir: str,
    ) -> None:
        variant_to_model_id = {
            "0.6b": "Qwen/Qwen3-ASR-0.6B",
            "1.7b": "Qwen/Qwen3-ASR-1.7B",
        }
        provider = _ui_value_to_provider(provider_ui)
        path_or_id = (
            variant_to_model_id[model_variant]
            if provider == "qwen3_asr"
            else model_dir or str(default_lightweight_model_dir(model_variant))
        )
        resolved_binary_path = binary_path or (
            str(default_lightweight_binary_path()) if provider == "qwen_asr_cli" else ""
        )
        updated = replace(
            self._config,
            hotkey=hotkey,
            model=replace(
                self._config.model,
                provider=provider,
                variant=model_variant,
                path_or_id=path_or_id,
                device=device,
                binary_path=resolved_binary_path,
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


def _provider_to_ui_value(provider: str) -> str:
    return "lightweight" if provider == "qwen_asr_cli" else "python"


def _ui_value_to_provider(provider_ui: str) -> str:
    return "qwen_asr_cli" if provider_ui == "lightweight" else "qwen3_asr"
