"""
Test s2t pipeline - English + Chinese.

English: hf-internal-testing/librispeech_asr_demo
Chinese: google/fleurs cmn_hans_cn
"""

import os
import re
import sys

import jiwer
import numpy as np
from datasets import load_dataset

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from s2t import transcription

HF_TOKEN = os.environ.get("HF_TOKEN", "")

transcription.load_model()


def resample(arr, orig_sr, target_sr=16000):
    if orig_sr == target_sr:
        return arr
    import librosa

    return librosa.resample(arr.astype(np.float32), orig_sr=orig_sr, target_sr=target_sr)


def _normalize_zh(text: str) -> str:
    text = text.replace(" ", "")
    text = re.sub(r"""[，。、；：！？「」『』《》""''…—\-,.\!\?:;]""", "", text)
    return text.strip()


def run_section(title, samples, lang_arg, ref_key, ref_transform=None, use_cer=False):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)
    hyps, refs = [], []
    for i, sample in enumerate(samples):
        arr = np.array(sample["audio"]["array"], dtype=np.float32)
        sr = sample["audio"]["sampling_rate"]
        arr = resample(arr, sr)
        ref_raw = sample[ref_key].strip()
        hyp_raw = transcription.transcribe(arr, language=lang_arg).strip()
        if ref_transform:
            ref_raw = ref_transform(ref_raw)
            hyp_raw = ref_transform(hyp_raw)
        print(f"[{i}]")
        print(f"  REF: {ref_raw}")
        print(f"  HYP: {hyp_raw}")
        ref_norm = _normalize_zh(ref_raw) if use_cer else ref_raw
        hyp_norm = _normalize_zh(hyp_raw) if use_cer else hyp_raw
        hyps.append(hyp_norm)
        refs.append(ref_norm)
    if use_cer:
        refs_spaced = [" ".join(list(r)) for r in refs]
        hyps_spaced = [" ".join(list(h)) for h in hyps]
        score = jiwer.wer(refs_spaced, hyps_spaced)
        label = "CER"
    else:
        score = jiwer.wer(refs, hyps)
        label = "WER"
    threshold = 0.20
    status = "PASS" if score < threshold else "FAIL"
    print(f"\n{label}: {score * 100:.1f}%  ->  {status}")
    return score, status


print("Loading English dataset (librispeech_asr_demo) ...")
en_ds = load_dataset("hf-internal-testing/librispeech_asr_demo", "clean", split="validation")
en_samples = list(en_ds.select(range(3)))

en_wer, en_status = run_section(
    "English - LibriSpeech (validation, 3 samples)",
    en_samples,
    lang_arg="English",
    ref_key="text",
    ref_transform=str.lower,
)

print("\nLoading Chinese dataset (google/fleurs zh_cn) ...")
zh_ds = load_dataset("google/fleurs", "cmn_hans_cn", split="test", token=HF_TOKEN, trust_remote_code=True)
zh_samples = list(zh_ds.select(range(3)))

zh_wer, zh_status = run_section(
    "Chinese - FLEURS cmn_hans_cn (test, 3 samples)",
    zh_samples,
    lang_arg="Chinese",
    ref_key="transcription",
    ref_transform=None,
    use_cer=True,
)

print(f"\n{'=' * 60}")
print("  SUMMARY")
print("=" * 60)
print(f"  English WER : {en_wer * 100:.1f}%  ->  {en_status}")
print(f"  Chinese CER : {zh_wer * 100:.1f}%  ->  {zh_status}")
overall = "PASS" if en_status == "PASS" and zh_status == "PASS" else "FAIL"
print(f"  Overall     : {overall}")
