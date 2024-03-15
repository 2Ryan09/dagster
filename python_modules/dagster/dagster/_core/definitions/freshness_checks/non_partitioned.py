from datetime import datetime
from typing import Optional, Sequence, Union

import pendulum

from dagster import _check as check
from dagster._core.definitions.asset_check_spec import AssetCheckSeverity
from dagster._core.definitions.metadata import (
    MetadataValue,
    TimestampMetadataValue,
)
from dagster._core.execution.context.compute import AssetExecutionContext
from dagster._utils.schedules import is_valid_cron_string, reverse_cron_string_iterator

from ..asset_check_result import AssetCheckResult
from ..asset_checks import AssetChecksDefinition
from ..assets import AssetsDefinition, SourceAsset
from ..events import CoercibleToAssetKey
from .utils import (
    DEFAULT_FRESHNESS_SEVERITY,
    asset_to_keys_iterable,
    ensure_no_duplicate_assets,
    get_last_updated_timestamp,
    retrieve_latest_record,
)


def build_non_partitioned_freshness_checks(
    *,
    assets: Sequence[Union[CoercibleToAssetKey, AssetsDefinition, SourceAsset]],
    freshness_cron: Optional[str] = None,
    maximum_lag_minutes: Optional[int] = None,
    severity: AssetCheckSeverity = DEFAULT_FRESHNESS_SEVERITY,
) -> Sequence[AssetChecksDefinition]:
    """For each provided asset, constructs a freshness check definition.

    An asset is considered fresh if it has been materialized or observed within a certain time
    window. The freshness_cron and maximum_lag_minutes parameters are used to define this time
    window. Freshness_cron defines the time at which the asset should have been materialized, and maximum_lag_minutes provides a tolerance for the range at which the asset can arrive.

    Let's say an asset kicks off materializing at 12:00 PM and takes 10 minutes to complete.
    Allowing for operational constraints and delays, the asset should always be materialized by
    12:30 PM. 12:00 PM provides the lower boundary, since the asset kicks off no earlier than this time.
    Then, we set freshness_cron to "30 12 * * *", which means the asset is expected by 12:30 PM, and maximum_lag_minutes to 30,
    which means the asset can be materialized no earlier than 12:00 PM.

    A time-window partitioned asset is considered fresh if the latest completed time window is materialized or observed.
    The freshness_cron parameter can be used to influence the time window that is checked. For example, if I have a daily partitioned asset,
    and I specify a freshness_cron for 12:00 PM, and I run the check at 1:00 AM March 12, I will check for the time window
    March 10 12:00 AM - March 11 12:00 AM, since the most recent completed tick of the cron was at 12:00 PM March 11.
    For partitioned assets, the maximum_lag_minutes parameter is not used.

    Args:
        assets (Sequence[Union[CoercibleToAssetKey, AssetsDefinition, SourceAsset]): The assets to construct checks for. For each passed in
            asset, there will be a corresponding constructed `AssetChecksDefinition`.
        freshness_cron (Optional[str]): The cron for which freshness is defined.
        maximum_lag_minutes (Optional[int]): The maximum lag in minutes that is acceptable for the asset.

    Returns:
        Sequence[AssetChecksDefinition]: A list of `AssetChecksDefinition` objects, each corresponding to an asset in the `assets` parameter.
    """
    ensure_no_duplicate_assets(assets)
    freshness_cron = check.opt_str_param(freshness_cron, "freshness_cron")
    check.param_invariant(
        is_valid_cron_string(freshness_cron) if freshness_cron else True,
        "freshness_cron",
        "Expect a valid cron string.",
    )
    maximum_lag_minutes = check.opt_int_param(maximum_lag_minutes, "maximum_lag_minutes")
    check.invariant(
        freshness_cron is not None or maximum_lag_minutes is not None,
        "At least one of freshness_cron or maximum_lag_minutes must be provided.",
    )
    severity = check.inst_param(severity, "severity", AssetCheckSeverity)

    return [
        check
        for asset in assets
        for check in _build_freshness_check_for_asset(
            asset,
            freshness_cron=freshness_cron,
            maximum_lag_minutes=maximum_lag_minutes,
            severity=severity,
        )
    ]


def _build_freshness_check_for_asset(
    asset: Union[CoercibleToAssetKey, AssetsDefinition, SourceAsset],
    freshness_cron: Optional[str],
    maximum_lag_minutes: Optional[int],
    severity: AssetCheckSeverity,
) -> Sequence[AssetChecksDefinition]:
    from ..decorators.asset_check_decorator import asset_check

    checks = []
    for asset_key in asset_to_keys_iterable(asset):

        @asset_check(
            asset=asset,
            description=f"Evaluates freshness for targeted asset. Cron: {freshness_cron}, Maximum lag minutes: {maximum_lag_minutes}.",
            name="freshness_check",
        )
        def the_check(context: AssetExecutionContext) -> AssetCheckResult:
            current_time = pendulum.now("UTC")
            current_timestamp = check.float_param(current_time.timestamp(), "current_time")
            last_cron_tick = get_latest_completed_cron_tick(freshness_cron, current_time, None)
            lower_search_bound = pendulum.instance(last_cron_tick or current_time).subtract(
                minutes=maximum_lag_minutes or 0
            )
            latest_record = retrieve_latest_record(context.instance, asset_key, partition_key=None)
            last_updated_timestamp = get_last_updated_timestamp(latest_record)

            if last_updated_timestamp is None:
                passed = True
                metadata = {}
                description = "Could not determine last updated timestamp"
            else:
                passed = lower_search_bound.timestamp() <= last_updated_timestamp
                metadata = {
                    "dagster/last_updated_timestamp": MetadataValue.timestamp(
                        last_updated_timestamp
                    )
                }

                if passed:
                    description = None
                else:
                    if last_cron_tick is None:
                        description = f"Last update was more than {maximum_lag_minutes} minutes ago"
                    else:
                        description = (
                            f"Last update was more than {maximum_lag_minutes} before last cron tick"
                        )
                        metadata["dagster/last_cron_tick"] = MetadataValue.timestamp(last_cron_tick)
                    metadata["dagster/minutes_late"] = TimestampMetadataValue(
                        (current_timestamp - last_updated_timestamp) // 60
                    )

            return AssetCheckResult(
                passed=passed, severity=severity, description=description, metadata=metadata
            )

        checks.append(the_check)

    return checks


def get_latest_completed_cron_tick(
    freshness_cron: Optional[str], current_time: datetime, timezone: Optional[str]
) -> Optional[datetime]:
    if not freshness_cron:
        return None

    cron_iter = reverse_cron_string_iterator(
        end_timestamp=current_time.timestamp(),
        cron_string=freshness_cron,
        execution_timezone=timezone,
    )
    return pendulum.instance(next(cron_iter))
