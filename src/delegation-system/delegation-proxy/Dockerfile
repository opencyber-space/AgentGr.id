# Use official lightweight Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 9000

# Default command
CMD ["python3", "main.py"]
