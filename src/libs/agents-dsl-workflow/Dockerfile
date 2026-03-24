FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/

RUN pip3 install -r requirements.txt

# Copy the binary from builder stage
COPY . /app/

EXPOSE 9100

# Run the binary
ENTRYPOINT ["python3", "main.py"]
