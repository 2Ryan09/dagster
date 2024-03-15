# pyright: reportPrivateImportUsage=false

import pendulum
import pytest
from dagster import (
    asset,
)
from dagster._core.definitions.asset_check_spec import AssetCheckSeverity
from dagster._core.definitions.asset_out import AssetOut
from dagster._core.definitions.decorators.asset_decorator import multi_asset
from dagster._core.definitions.events import AssetKey
from dagster._core.definitions.freshness_checks.time_window_partitioned import (
    build_time_window_partitioned_freshness_checks,
)
from dagster._core.definitions.source_asset import SourceAsset
from dagster._core.definitions.time_window_partitions import (
    DailyPartitionsDefinition,
)
from dagster._core.instance import DagsterInstance

from .conftest import add_new_event, assert_check_result


def test_params() -> None:
    @asset(
        partitions_def=DailyPartitionsDefinition(
            start_date=pendulum.datetime(2020, 1, 1, 0, 0, 0, tz="UTC")
        )
    )
    def my_partitioned_asset():
        pass

    result = build_time_window_partitioned_freshness_checks(assets=[my_partitioned_asset])
    assert len(result) == 1
    assert next(iter(result[0].check_keys)).asset_key == my_partitioned_asset.key

    result = build_time_window_partitioned_freshness_checks(
        assets=[my_partitioned_asset.key], offset_minutes=10
    )
    assert len(result) == 1
    assert next(iter(result[0].check_keys)).asset_key == my_partitioned_asset.key

    src_asset = SourceAsset("source_asset")
    result = build_time_window_partitioned_freshness_checks(assets=[src_asset], offset_minutes=10)
    assert len(result) == 1
    assert next(iter(result[0].check_keys)).asset_key == src_asset.key

    result = build_time_window_partitioned_freshness_checks(
        assets=[my_partitioned_asset, src_asset], offset_minutes=10
    )
    assert len(result) == 2
    assert {next(iter(checks_def.check_keys)).asset_key for checks_def in result} == {
        my_partitioned_asset.key,
        src_asset.key,
    }

    with pytest.raises(Exception, match="Found duplicate assets"):
        build_time_window_partitioned_freshness_checks(
            assets=[my_partitioned_asset, my_partitioned_asset], offset_minutes=10
        )

    @multi_asset(
        outs={
            "my_partitioned_asset": AssetOut(),
            "b": AssetOut(),
        },
        can_subset=True,
        partitions_def=DailyPartitionsDefinition(
            start_date=pendulum.datetime(2020, 1, 1, 0, 0, 0, tz="UTC")
        ),
    )
    def my_multi_asset(context):
        pass

    result = build_time_window_partitioned_freshness_checks(assets=[my_multi_asset])
    assert len(result) == 2
    assert {next(iter(checks_def.check_keys)).asset_key for checks_def in result} == set(
        my_multi_asset.keys
    )

    with pytest.raises(Exception, match="Found duplicate assets"):
        build_time_window_partitioned_freshness_checks(
            assets=[my_multi_asset, my_multi_asset], offset_minutes=10
        )

    with pytest.raises(Exception, match="Found duplicate assets"):
        build_time_window_partitioned_freshness_checks(
            assets=[my_multi_asset, my_partitioned_asset], offset_minutes=10
        )

    coercible_key = "blah"
    result = build_time_window_partitioned_freshness_checks(
        assets=[coercible_key], offset_minutes=10
    )
    assert len(result) == 1
    assert next(iter(result[0].check_keys)).asset_key == AssetKey.from_coercible(coercible_key)

    with pytest.raises(Exception, match="Found duplicate assets"):
        build_time_window_partitioned_freshness_checks(
            assets=[coercible_key, coercible_key], offset_minutes=10
        )

    regular_asset_key = AssetKey("regular_asset_key")
    result = build_time_window_partitioned_freshness_checks(
        assets=[regular_asset_key], offset_minutes=10
    )
    assert len(result) == 1
    assert next(iter(result[0].check_keys)).asset_key == regular_asset_key

    with pytest.raises(Exception, match="Found duplicate assets"):
        build_time_window_partitioned_freshness_checks(
            assets=[regular_asset_key, regular_asset_key], offset_minutes=10
        )


def test_result_time_window_partitioned(
    pendulum_aware_report_dagster_event: None,
    instance: DagsterInstance,
) -> None:
    """Move time forward and backward, with a freshness check parameterized with a cron, and ensure that the check passes and fails as expected."""
    partitions_def = DailyPartitionsDefinition(
        start_date=pendulum.datetime(2020, 1, 1, 0, 0, 0, tz="UTC")
    )

    @asset(partitions_def=partitions_def)
    def my_asset():
        pass

    start_time = pendulum.datetime(2021, 1, 1, 1, 0, 0, tz="UTC")

    freshness_checks = build_time_window_partitioned_freshness_checks(
        assets=[my_asset],
        offset_minutes=10,
    )

    freeze_datetime = start_time
    with pendulum.test(freeze_datetime):
        # With no events, check fails.
        assert_check_result(my_asset, instance, freshness_checks, AssetCheckSeverity.WARN, False)

        # Add an event for an old partition. Still fails
        add_new_event(instance, my_asset.key, "2020-12-30")
        assert_check_result(my_asset, instance, freshness_checks, AssetCheckSeverity.WARN, False)

        # Go back in time and add an event for the most recent completed partition.
        add_new_event(instance, my_asset.key, "2020-12-31")
        assert_check_result(my_asset, instance, freshness_checks, AssetCheckSeverity.WARN, True)

    # Advance a full day. By now, we would expect a new event to have been added.
    # Since that is not the case, we expect the check to fail.
    freeze_datetime = freeze_datetime.add(days=1)
    with pendulum.test(freeze_datetime):
        assert_check_result(my_asset, instance, freshness_checks, AssetCheckSeverity.WARN, False)

        # Again, go back in time, and add an event for the most recently completed time window.
        # Now we expect the check to pass.
        add_new_event(instance, my_asset.key, "2021-01-01")
        assert_check_result(my_asset, instance, freshness_checks, AssetCheckSeverity.WARN, True)


# Test for providing non-partitioned and non-time-window-partitioned assets to build_time_window_partitioned_freshness_checks
# Test for providing multiple kinds of events, both observables and materializations.
