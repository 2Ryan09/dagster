# start_marker
from dagster import (
    AssetExecutionContext,
    BackfillPolicy,
    DailyPartitionsDefinition,
    InputContext,
    IOManager,
    OutputContext
    asset,
)


class MyIOManager(IOManager):
    def load_input(self, context: InputContext):
        start_datetime, end_datetime = context.asset_partitions_time_window
        return read_data_in_datetime_range(start_datetime, end_datetime)

    def handle_output(self, context: OutputContext, obj):
        start_datetime, end_datetime = context.asset_partitions_time_window
        return overwrite_data_in_datetime_range(start_datetime, end_datetime, obj)


@asset(
    partitions_def=DailyPartitionsDefinition(start_date="2020-01-01"),
    backfill_policy=BackfillPolicy.single_run(),
)
def events(context: AssetExecutionContext, raw_events):
    output_data = compute_events_from_raw_events(raw_events)
    return output_data


# end_marker


def read_data_in_datetime_range(*args):
    ...


def overwrite_data_in_datetime_range(*args):
    ...
