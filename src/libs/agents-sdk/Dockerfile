FROM python:latest

WORKDIR /app

COPY requirements.txt /app

RUN pip3 install -r requirements.txt


COPY . /app/

ENTRYPOINT [ "python3", "search_agent.py" ]