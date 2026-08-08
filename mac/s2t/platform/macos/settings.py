from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import messagebox, ttk

from ...core.config import (
    AppConfig,
    ConfigError,
    MeetingConfig,
    default_lightweight_binary_path,
    default_lightweight_model_dir,
    default_transcript_dir,
    save_config,
)


def _input_device_names() -> list[str]:
    try:
        from .meeting_audio import list_input_devices

        return [name for _idx, name, _ch in list_input_devices()]
    except Exception:
        return []


class SettingsWindow:
    def __init__(self, config: AppConfig, config_path: Path, on_saved) -> None:
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
        root.geometry("620x600")
        root.resizable(False, False)

        backend_var = tk.StringVar(value=_provider_to_ui(self._config.model.provider))
        hotkey_var = tk.StringVar(value=self._config.hotkey)
        model_var = tk.StringVar(value=self._config.model.variant or "0.6b")
        device_var = tk.StringVar(value=self._config.model.device)
        language_var = tk.StringVar(value=self._config.language)
        binary_path_var = tk.StringVar(value=self._config.model.binary_path)
        model_dir_var = tk.StringVar(
            value=(
                self._config.model.path_or_id
                if self._config.model.provider == "qwen_asr_cli"
                else str(default_lightweight_model_dir(self._config.model.variant or "0.6b"))
            )
        )
        # Meeting device pickers.
        device_names = _input_device_names()
        MIC_AUTO = "Auto (default input)"
        mic_choices = [MIC_AUTO] + device_names
        mic_device_var = tk.StringVar(value=self._config.meeting.mic_device or MIC_AUTO)

        # Their-audio source: a friendly picker mapping to (system_source, system_device).
        SYS_TAP = "System audio — auto (recommended)"
        SYS_OFF = "Off (my mic only)"
        sys_choices = [SYS_TAP, SYS_OFF] + device_names
        if self._config.meeting.system_source == "tap":
            sys_current = SYS_TAP
        elif self._config.meeting.system_source == "off":
            sys_current = SYS_OFF
        else:
            sys_current = self._config.meeting.system_device or SYS_TAP
        system_source_var = tk.StringVar(value=sys_current)
        self._MIC_AUTO = MIC_AUTO
        self._SYS_TAP = SYS_TAP
        self._SYS_OFF = SYS_OFF
        transcript_enabled_var = tk.BooleanVar(value=self._config.transcript.enabled)
        transcript_dir_var = tk.StringVar(
            value=self._config.transcript.output_dir or str(default_transcript_dir())
        )
        transcript_prefix_var = tk.StringVar(value=self._config.transcript.filename_prefix)

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        row = 0

        def row_label(text):
            nonlocal row
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=(0, 8))

        def row_widget(widget_factory, *args, **kwargs):
            nonlocal row
            w = widget_factory(frame, *args, **kwargs)
            w.grid(row=row, column=1, sticky="ew", pady=(0, 8))
            row += 1
            return w

        ttk.Label(frame, text="— Meeting —", font=("", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        row_label("My Mic")
        row_widget(ttk.Combobox, textvariable=mic_device_var, values=mic_choices, state="readonly")

        row_label("Their Audio")
        row_widget(ttk.Combobox, textvariable=system_source_var, values=sys_choices, state="readonly")

        row_label("Language")
        row_widget(ttk.Entry, textvariable=language_var)

        # Transcript section
        ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frame, text="— Transcript —", font=("", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        ttk.Label(frame, text="Save transcript").grid(row=row, column=0, sticky="w", pady=(0, 8))
        ttk.Checkbutton(frame, variable=transcript_enabled_var).grid(row=row, column=1, sticky="w", pady=(0, 8))
        row += 1

        ttk.Label(frame, text="Transcript folder").grid(row=row, column=0, sticky="w", pady=(0, 8))
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=row, column=1, sticky="ew", pady=(0, 8))
        dir_frame.columnconfigure(0, weight=1)
        ttk.Entry(dir_frame, textvariable=transcript_dir_var).grid(row=0, column=0, sticky="ew")

        def _browse_dir():
            from tkinter import filedialog

            chosen = filedialog.askdirectory(initialdir=transcript_dir_var.get() or str(default_transcript_dir()))
            if chosen:
                transcript_dir_var.set(chosen)

        ttk.Button(dir_frame, text="Browse…", command=_browse_dir).grid(row=0, column=1, padx=(6, 0))
        row += 1

        ttk.Label(frame, text="Filename prefix").grid(row=row, column=0, sticky="w", pady=(0, 8))
        row_widget(ttk.Entry, textvariable=transcript_prefix_var)

        # Advanced section (collapsed-ish, just below)
        ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frame, text="— Model & Advanced —", font=("", 12, "bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        row_label("Backend")
        backend_combo = row_widget(ttk.Combobox, textvariable=backend_var, values=["python", "lightweight"], state="readonly")

        row_label("Model")
        row_widget(ttk.Combobox, textvariable=model_var, values=["0.6b", "1.7b"], state="readonly")

        row_label("Compute")
        device_combo = row_widget(ttk.Combobox, textvariable=device_var, values=["auto", "cpu", "gpu"], state="readonly")

        row_label("Hotkey (optional)")
        row_widget(ttk.Entry, textvariable=hotkey_var)

        ttk.Label(
            frame,
            text="Their Audio 'auto' captures system sound without changing your output device — "
                 "works with AirPods or built-in speakers and follows switches automatically.",
            wraplength=560,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))
        row += 1

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btn_frame, text="Cancel", command=root.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(
            btn_frame,
            text="Save",
            command=lambda: self._save_and_close(
                root=root,
                provider_ui=backend_var.get().strip(),
                hotkey=hotkey_var.get().strip(),
                model_variant=model_var.get().strip(),
                device=device_var.get().strip(),
                language=language_var.get().strip(),
                mic_device=mic_device_var.get().strip(),
                system_source_choice=system_source_var.get().strip(),
                binary_path=binary_path_var.get().strip(),
                model_dir=model_dir_var.get().strip(),
                transcript_enabled=transcript_enabled_var.get(),
                transcript_dir=transcript_dir_var.get().strip(),
                transcript_prefix=transcript_prefix_var.get().strip(),
            ),
        ).pack(side="right")

        def _update_backend(*_):
            if backend_var.get() == "lightweight":
                device_combo.configure(values=["auto", "cpu"])
                if device_var.get() == "gpu":
                    device_var.set("auto")
            else:
                device_combo.configure(values=["auto", "cpu", "gpu"])

        backend_var.trace_add("write", _update_backend)
        _update_backend()
        root.mainloop()

    def _save_and_close(self, *, root, provider_ui, hotkey, model_variant, device,
                         language, mic_device, system_source_choice, binary_path, model_dir,
                         transcript_enabled, transcript_dir, transcript_prefix) -> None:
        # Map friendly pickers back to config values.
        if mic_device == self._MIC_AUTO:
            mic_device = ""
        if system_source_choice == self._SYS_TAP:
            system_source, system_device = "tap", ""
        elif system_source_choice == self._SYS_OFF:
            system_source, system_device = "off", ""
        else:
            system_source, system_device = "device", system_source_choice
        variant_to_model_id = {
            "0.6b": "Qwen/Qwen3-ASR-0.6B",
            "1.7b": "Qwen/Qwen3-ASR-1.7B",
        }
        provider = _ui_to_provider(provider_ui)
        path_or_id = (
            variant_to_model_id[model_variant]
            if provider == "qwen3_asr"
            else model_dir or str(default_lightweight_model_dir(model_variant))
        )
        resolved_binary = binary_path or (str(default_lightweight_binary_path()) if provider == "qwen_asr_cli" else "")
        from ...core.config import TranscriptConfig
        updated = replace(
            self._config,
            hotkey=hotkey or self._config.hotkey,
            language=language or self._config.language,
            model=replace(
                self._config.model,
                provider=provider,
                variant=model_variant,
                path_or_id=path_or_id,
                device=device,
                binary_path=resolved_binary,
            ),
            meeting=replace(
                self._config.meeting,
                mic_device=mic_device,
                system_source=system_source,
                system_device=system_device,
            ),
            transcript=TranscriptConfig(
                enabled=transcript_enabled,
                output_dir=transcript_dir if transcript_dir != str(default_transcript_dir()) else "",
                filename_prefix=transcript_prefix or "meeting",
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


def _provider_to_ui(provider: str) -> str:
    return "lightweight" if provider == "qwen_asr_cli" else "python"


def _ui_to_provider(ui: str) -> str:
    return "qwen_asr_cli" if ui == "lightweight" else "qwen3_asr"
