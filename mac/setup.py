"""py2app build script for the s2t macOS menu-bar app.

Build a double-clickable .app that links to this venv (fast, self-use):

    .venv/bin/python setup.py py2app -A

The -A (alias) mode symlinks into the current venv instead of copying the
multi-GB torch/transformers stack, so it builds in seconds and always uses the
same model cache. It only runs on this machine (not distributable), which is
exactly what we want for a personal meeting-transcription tool.
"""
from setuptools import setup

APP = ["run_app.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "s2t",
        "CFBundleDisplayName": "s2t Meeting Transcriber",
        "CFBundleIdentifier": "com.zhenyxu.s2t",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        # Menu-bar-only app: no Dock icon, no main window.
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "s2t records your microphone to transcribe meetings locally.",
        "NSAudioCaptureUsageDescription": "s2t captures system audio to transcribe the other participants locally.",
        "NSHighResolutionCapable": True,
    },
}

setup(
    app=APP,
    name="s2t",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
