from typing import Sequence, Union, cast

import pendulum

from dagster import _check as check
from dagster._core.definitions.asset_check_spec import AssetCheckSeverity
from dagster._core.definitions.decorators.asset_check_decorator import asset_check
from dagster._core.definitions.metadata import TimestampMetadataValue
from dagster._core.execution.context.compute import AssetExecutionContext

from ..asset_check_result import AssetCheckResult
from ..asset_checks import AssetChecksDefinition
from ..assets import AssetsDefinition, SourceAsset
from ..events import CoercibleToAssetKey
from ..time_window_partitions import TimeWindowPartitionsDefinition
from .utils import (
    DEFAULT_FRESHNESS_SEVERITY,
    asset_to_keys_iterable,
    ensure_no_duplicate_assets,
    get_last_updated_timestamp,
    retrieve_latest_record,
)


def build_time_window_partitioned_freshness_checks(
    *,
    assets: Sequence[Union[SourceAsset, CoercibleToAssetKey, AssetsDefinition]],
    offset_minutes: int = 0,
    severity: AssetCheckSeverity = DEFAULT_FRESHNESS_SEVERITY,
) -> Sequence[AssetChecksDefinition]:
    """For each provided time-window partitioned asset, constructs a freshness check definition.

    Will emit a runtime error for any assets that are not time-window partitioned.

    An asset is considered fresh if its most recent time window is materialized or observed within
    the specified offset.

    For example, let's say I have a daily time-window partitioned asset, and I specify an offset of
    60 minutes. This means that I expect March 11 to March 12 data to be seen by March 13 1:00 AM.
    If the data is not seen, the asset check will not pass.

    Args:
        assets (Sequence[Union[CoercibleToAssetKey, AssetsDefinition, SourceAsset]): The assets to
            construct checks for. For each passed in asset, there will be a corresponding
            constructed `AssetChecksDefinition`.
        offset_minutes (int): The number of minutes to allow for the asset to be considered fresh. Defaults to 0.


    Returns:
        Sequence[AssetChecksDefinition]: A list of `AssetChecksDefinition` objects, each corresponding to an asset in the `assets` parameter.
    """
    ensure_no_duplicate_assets(assets)
    offset_minutes = check.int_param(offset_minutes, "offset_minutes")
    severity = check.inst_param(severity, "severity", AssetCheckSeverity)

    return [
        check
        for asset in assets
        for check in _build_freshness_checks_for_asset(asset, offset_minutes, severity)
    ]


def _build_freshness_checks_for_asset(
    asset: Union[SourceAsset, CoercibleToAssetKey, AssetsDefinition],
    offset_minutes: int,
    severity: AssetCheckSeverity,
) -> Sequence[AssetChecksDefinition]:
    checks = []
    for asset_key in asset_to_keys_iterable(asset):

        @asset_check(
            asset=asset_key,
            description=f"Evaluates freshness for targeted asset. Offset: {offset_minutes} minutes.",
            name="freshness_check",
        )
        def the_check(context: AssetExecutionContext) -> AssetCheckResult:
            current_time = pendulum.now()
            current_timestamp = check.float_param(current_time.timestamp(), "current_time")
            partitions_def: TimeWindowPartitionsDefinition = cast(
                TimeWindowPartitionsDefinition,
                check.inst_param(
                    context.job_def.asset_layer.asset_graph.get(asset_key).partitions_def,
                    "partitions_def",
                    TimeWindowPartitionsDefinition,
                ),
            )
            offset_adjusted_time = current_time.subtract(minutes=offset_minutes)
            time_window = partitions_def.get_prev_partition_window(offset_adjusted_time)
            if not time_window:
                return AssetCheckResult(
                    passed=True,
                    description="No partitions have been completed yet.",
                    severity=severity,
                )
            partition_key = partitions_def.get_partition_key_range_for_time_window(
                time_window
            ).start
            latest_record = retrieve_latest_record(context.instance, asset_key, partition_key)
            passed = latest_record is not None
            if passed:
                last_updated_timestamp = check.float_param(
                    get_last_updated_timestamp(latest_record), "last_updated_timestamp"
                )
                metadata = {
                    "dagster/last_updated_timestamp": TimestampMetadataValue(
                        last_updated_timestamp
                    ),
                }
                description = None
            else:
                metadata = {
                    "dagster/minutes_late": TimestampMetadataValue(
                        (current_timestamp - time_window.end.timestamp()) // 60 + offset_minutes
                    ),
                }
                description = f"Latest partition is {current_timestamp - time_window.end.timestamp()//60} minutes late."

            return AssetCheckResult(
                passed=passed,
                description=description,
                metadata=metadata,
                severity=severity,
            )

        checks.append(the_check)
    return checks
