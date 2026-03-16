from server import app
import cache


def main():
    # Load cached weapon/attribute data from disk (refreshes from API if stale).
    cache.init_cache()
    # Starts the Flask API server on port 5000.
    # The React frontend (frontend/) proxies /api requests here via Vite's dev server.
    # Start the frontend separately: cd frontend && npm run dev
    print("Starting Riven Market API on http://localhost:5000")
    app.run(port=5000, debug=True)


if __name__ == "__main__":
    main()
