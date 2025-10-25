web: gunicorn gamma_intelligence.wsgi --timeout 300 --keep-alive 5 --max-requests 100 --max-requests-jitter 10
worker: python manage.py run_pipeline
worker-edgar: python manage.py edgar_scheduler_2