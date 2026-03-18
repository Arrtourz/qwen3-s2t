import os


collect_ignore_glob = []

if os.environ.get("S2T_RUN_LINUX_E2E") != "1":
    collect_ignore_glob.append("test_pipeline.py")
