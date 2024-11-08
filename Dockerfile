FROM python:3.11-slim


WORKDIR /bottec_test
COPY requirements.txt .
RUN pip install -r requirements.txt


COPY . .


CMD ["python", "main.py"]