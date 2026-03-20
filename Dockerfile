FROM python:3.11-slim

LABEL maintainer="nazar"
LABEL description="Nazar - Autonomous Testing Tool"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY nazar/ nazar/

RUN pip install --no-cache-dir .

WORKDIR /project

ENTRYPOINT ["nazar"]
CMD ["auto", "."]
