FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home runner && mkdir /app/runs && chown runner /app/runs
COPY datasets ./datasets
USER runner
ENTRYPOINT ["agent-lab"]
CMD ["run", "--strategy", "baseline", "--output", "runs/baseline"]
