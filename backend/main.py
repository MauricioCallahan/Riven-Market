import os
import logging
from dotenv import load_dotenv
from api.routes import app
from services import cache_service as cache
from services.meta_tiers import init as init_meta_tiers


def main():
    load_dotenv()
    log_level = os.environ.get("LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s: %(message)s")
    # Load cached weapon/attribute data from disk (refreshes from API if stale).
    cache.init_cache()
    # Load meta tier data (Incarnon weapons + Overframe rankings).
    init_meta_tiers()
    # Starts the Flask API server on port 5000.
    # The React frontend (frontend/) proxies /api requests here via Vite's dev server.
    # Start the frontend separately: cd frontend && npm run dev
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    print("Starting Riven Market API on http://localhost:5000")
    app.run(port=5000, debug=debug)


if __name__ == "__main__":
    main()
