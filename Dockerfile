FROM python:3.10-alpine

WORKDIR /app
ADD src ./src
ADD pyproject.toml .
ADD setup.py .

RUN pip install .[slurm,aws] --no-cache-dir
