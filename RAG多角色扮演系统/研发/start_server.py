import uvicorn
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    print("Starting server...", file=sys.stdout)
    sys.stdout.flush()
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8080,
            log_level="debug",
            reload=False
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.stderr.flush()