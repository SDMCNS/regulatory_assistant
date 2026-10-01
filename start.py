import sys
import argparse
import subprocess
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Startup script for Regulation Assistant")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # API command
    api_parser = subparsers.add_parser("api", help="Start the FastAPI server")
    
    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Run the data ingestion pipeline")

    # Pass remaining arguments to the sub-scripts
    args, unknown = parser.parse_known_args()

    project_root = Path(__file__).resolve().parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Load custom settings if available
    config_file = project_root / "user.settings.conf"
    import os
    if config_file.exists():
        print(f"Loading custom settings from {config_file.name}...")
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        # Ensure the prefix expected by pydantic_settings is present
                        if not key.startswith("REG_INGEST_"):
                            key = f"REG_INGEST_{key}"
                        os.environ[key] = val

    if args.command == "api":
        import uvicorn
        print("Starting FastAPI server...")
        uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
    elif args.command == "ingest":
        print("Starting Ingestion Pipeline...")
        cmd = [sys.executable, "-m", "ingestion.run_all"] + unknown
        subprocess.run(cmd, check=True)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
