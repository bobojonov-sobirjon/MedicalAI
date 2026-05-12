"""
Gunicorn config for production. Use: gunicorn -c gunicorn.conf.py config.wsgi:application

Default worker timeout is 30s — RuTronix OCR often needs 40–120s, which causes WORKER TIMEOUT
and SystemExit in logs. Override with env GUNICORN_TIMEOUT (seconds).
"""
import os

bind = os.environ.get("GUNICORN_BIND", "unix:/run/medical.sock")
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
worker_class = "sync"
# Wall-clock per request; must exceed RuTronix vision (see RUTRONIX_VISION_* in Django settings).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "180"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "120"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
accesslog = os.environ.get("GUNICORN_ACCESSLOG", "-")
errorlog = os.environ.get("GUNICORN_ERRORLOG", "-")
capture_output = os.environ.get("GUNICORN_CAPTURE_OUTPUT", "true").lower() in ("1", "true", "yes")
