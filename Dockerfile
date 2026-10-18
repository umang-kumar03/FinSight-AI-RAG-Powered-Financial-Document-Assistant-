FROM python:3.11-slim

WORKDIR /app

COPY requirements*.txt ./
# Optional trusted CA is mounted only during builds behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=custom_ca \
    if [ -f /run/secrets/custom_ca ]; then export PIP_CERT=/run/secrets/custom_ca; fi; \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
