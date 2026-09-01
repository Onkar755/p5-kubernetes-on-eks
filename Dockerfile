FROM python:3.11-slim

WORKDIR /code

RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home appuser

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir -r /code/requirements.txt

COPY ./app /code/app

RUN chown -R appuser:appgroup /code

USER 10001:10001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]