FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py main.py config.py runtime.txt ./
COPY core ./core
COPY data ./data
COPY notifications ./notifications
COPY pages ./pages
COPY scripts ./scripts
COPY downloads ./downloads

# Copy the pre-seeded database with portfolio data
COPY portfolio.db ./portfolio.db

EXPOSE 8080

CMD ["sh", "-c", "streamlit run app.py --server.port ${PORT:-8080} --server.address 0.0.0.0 --server.enableCORS false"]