# Deprecated: use repo root gunicorn.conf.py (env GUNICORN_TIMEOUT, WEB_CONCURRENCY).
bind = "unix:/run/medical.sock"
workers = 3
worker_class = "sync"
timeout = 180
graceful_timeout = 120
keepalive = 5
