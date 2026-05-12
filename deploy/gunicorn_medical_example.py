# Example Gunicorn config for MedicalAI (copy path into systemd or use -c).
# Default Gunicorn timeout=30 kills workers during RuTronix OCR; use >= 120 for vision routes.
bind = "unix:/run/medical.sock"
workers = 3
worker_class = "sync"
timeout = 120
graceful_timeout = 60
keepalive = 5
