"""Startup script for the Simulasi Sidang MK server."""
import sys
import os

# Ensure the simulasi directory is in the path
simulasi_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, simulasi_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        app_dir=simulasi_dir,
    )
