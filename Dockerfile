from python:3.10-slim

WORKDIR /app
ADD src ./src
ADD pyproject.toml .
ADD setup.py .

RUN pip install . --no-cache-dir
