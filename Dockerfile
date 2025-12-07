FROM python:3.12-slim

WORKDIR /app

# Install UV and curl
RUN apt-get update && apt-get install -y curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml ./
RUN uv sync --no-dev

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh

EXPOSE 8000
ENV PYTHONUNBUFFERED=1

CMD ["./entrypoint.sh"]
