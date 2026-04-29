import os

bind = f"0.0.0.0:{os.environ.get('FLASK_PORT', '5003')}"
workers = 1          # MUST be 1 — app uses in-memory dicts for table state
threads = 4          # handle concurrency via threads, not worker processes
timeout = 30
keepalive = 5
max_requests = 10000
max_requests_jitter = 500
accesslog = "-"
errorlog = "-"
loglevel = "info"
