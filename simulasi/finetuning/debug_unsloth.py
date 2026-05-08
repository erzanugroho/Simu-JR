import sys
import os

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("--- DEBUG START ---", flush=True)
print(f"Python executable: {sys.executable}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)

try:
    print("Importing torch...", end="", flush=True)
    import torch
    print(f" OK ({torch.__version__})", flush=True)
    
    print("Importing transformers...", end="", flush=True)
    import transformers
    print(f" OK ({transformers.__version__})", flush=True)
    
    print("Importing unsloth...", end="", flush=True)
    from unsloth import FastLanguageModel
    print(" OK", flush=True)
    
    print("--- SUCCESS ---", flush=True)
except Exception as e:
    print(f"\n!!! FAILED with Exception: {type(e).__name__}: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
except SystemExit as e:
    print(f"\n!!! FAILED with SystemExit: {e.code}", flush=True)
    sys.exit(e.code)
except BaseException as e:
    print(f"\n!!! FAILED with BaseException: {type(e).__name__}: {e}", flush=True)
    sys.exit(1)
