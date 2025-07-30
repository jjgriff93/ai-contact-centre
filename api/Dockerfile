FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Copy the application into the container.
COPY . /app

# Install the project into `/app`
WORKDIR /app
RUN uv sync --frozen --no-cache --compile-bytecode --no-dev

# Run the application.
CMD ["/app/.venv/bin/fastapi", "run", "app/main.py", "--port", "80"]
