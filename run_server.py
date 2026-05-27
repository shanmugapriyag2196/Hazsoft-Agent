#!/usr/bin/env python
"""Run server with .env loaded"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env BEFORE any other imports
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)

# Now import and run
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.index:app", host="0.0.0.0", port=8000, reload=True)