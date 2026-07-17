# PythonAnywhere Deployment Procfile
# Format: web: command to run your web app
# worker: command for background jobs (cron)

web: streamlit run --server.port=$PORT --server.enableCORS=false app.py
worker: python main.py