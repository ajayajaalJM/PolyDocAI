# docker/

Optional Docker Compose configurations for local development services.

## docker-compose.dev.yml

Starts Ollama alongside optional app services. The frontend and backend can still be run natively via `./scripts/dev.sh`.

```bash
docker compose -f docker/docker-compose.dev.yml up -d ollama
ollama pull llama3.2
```
