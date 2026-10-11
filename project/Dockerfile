FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libxcb1 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.api.lock ./
RUN pip install --no-cache-dir -r requirements.api.lock
COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
CMD ["uvicorn", "surveillance.api.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
