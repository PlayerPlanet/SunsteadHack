# Phase-2 Full-Run Container for SunsteadHack
# Runs the complete optimization loop: propose → benchmark → pore gate → log.
# Currently uses fixtures (Story B awaits real proposer/benchmark/pore/logclient).

FROM python:3.11-slim

# Install the cleanroom package and its dependencies
WORKDIR /app
COPY ../../cleanroom /app/cleanroom
COPY ../../pyproject.toml /app/

# Install cleanroom and dependencies
RUN pip install --no-cache-dir -e .

# Copy entrypoint
COPY run-entrypoint.sh /
RUN chmod +x /run-entrypoint.sh

# Entrypoint: run the loop
ENTRYPOINT ["/run-entrypoint.sh"]
