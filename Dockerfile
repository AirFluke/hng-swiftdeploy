# SwiftDeploy API Service
FROM python:3.12-alpine

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# Copy application
COPY app/main.py .

# Set ownership
RUN chown -R appuser:appgroup /app

USER appuser

# Default env vars (overridden by docker-compose)
ENV MODE=stable
ENV APP_VERSION=1.0.0
ENV APP_PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:${APP_PORT}/healthz || exit 1

CMD ["python", "main.py"]
