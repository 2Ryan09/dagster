import pandas as pd
from dagster_snowflake import SnowflakeResource

from dagster import asset


@asset
def iris_dataset(snowflake: SnowflakeResource) -> None:
    iris_df = pd.read_csv(
        "https://docs.dagster.io/assets/iris.csv",
        names=[
            "sepal_length_cm",
            "sepal_width_cm",
            "petal_length_cm",
            "petal_width_cm",
            "species",
        ],
    )

    with snowflake.get_connection() as conn:
        conn.cursor.execute("CREATE TABLE iris.iris_dataset AS SELECT * FROM iris_df")
