FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev libpq-dev build-essential curl && \
    pip install --upgrade pip setuptools wheel pyinstaller

# Copy application code
COPY . .

# Install Python requirements
RUN pip install -r requirements.txt

# Generate the binary (you can customize the name)
RUN pyinstaller --distpath=/app/dist/ main.py

# -------- Stage 2: Minimal runtime image --------
FROM python:3.12-slim

WORKDIR /app

# Copy the binary from builder stage
COPY --from=builder /app/dist/main /app

# Expose the Flask port (optional)
EXPOSE 5000

# Run the binary
ENTRYPOINT ["./main"]
