FROM python:3.11-slim
RUN pip install --no-cache-dir dbt-postgres==1.11.0
WORKDIR /dbt
ENV DBT_PROFILES_DIR=/dbt
ENTRYPOINT ["dbt"]
