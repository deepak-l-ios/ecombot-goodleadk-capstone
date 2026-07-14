FROM python:3.12-slim

WORKDIR /app

# System deps: gcc for psycopg2 compilation, libpq-dev for PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose Chainlit / ADK Web port
EXPOSE 8000

ENV PYTHONPATH=/app/src
ENV SESSION_BACKEND=memory
ENV VECTOR_BACKEND=memory

# Healthcheck: verify imports are clean
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0,'src'); from config.settings import settings; from routing import FAST_MODEL; print('ok')" || exit 1

# Default: run the ADK Web interface
# Override with: docker run ... chainlit run src/ui/chainlit_app.py
CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8000"]
