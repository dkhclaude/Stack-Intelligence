FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN useradd --create-home --uid 10001 pokewatch
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY dashboard ./dashboard
COPY config ./config
COPY .streamlit ./.streamlit
RUN pip install --no-deps . && mkdir -p /app/data && chown -R pokewatch /app/data
USER pokewatch

# Default command is the monitoring worker; the dashboard overrides it in compose.
CMD ["pokewatch", "worker"]
