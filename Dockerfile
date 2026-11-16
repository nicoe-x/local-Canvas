FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY . /app
RUN if [ -f /app/open_studio/pyproject.toml ]; then pip install --no-cache-dir -c /app/open_studio/requirements-tested.txt /app/open_studio; else pip install --no-cache-dir -c /app/requirements-tested.txt /app; fi && useradd --uid 10001 --create-home studio && mkdir -p /data && chown studio:studio /data
USER studio
ENV OPEN_STUDIO_DATA=/data OPEN_STUDIO_HOST=0.0.0.0 OPEN_STUDIO_PORT=8848
VOLUME ["/data"]
EXPOSE 8848
CMD ["open-comfy-studio"]
